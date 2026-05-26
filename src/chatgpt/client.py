"""
ChatGPT client — core interaction logic.

Sends messages, waits for responses, manages conversations.
Handles selector fallbacks and integrates human-like behavior.
"""

from __future__ import annotations

import asyncio
import re
import time

from patchright.async_api import Page

from src.chatgpt.model_registry import (
    list_switchable_models,
    normalize_model_token,
    resolve_requested_model,
)
from src.config import Config
from src.selectors import Selectors
from src.browser.human import human_type, human_click, thinking_pause, random_delay
from src.chatgpt.detector import (
    wait_for_response_complete,
    extract_last_response_via_copy,
    count_assistant_messages,
    get_latest_assistant_turn_signature,
    is_incomplete_response_text,
)
from src.chatgpt.image_handler import extract_images_from_response
from src.chatgpt.models import ChatResponse
from src.log import setup_logging

log = setup_logging("chatgpt_client")


class ChatGPTClient:
    """
    High-level client for interacting with the ChatGPT web interface.

    Requires a Playwright Page that is already logged in and on chatgpt.com.
    """

    def __init__(self, page: Page) -> None:
        self._page = page
        self._last_model_label = ""

    @property
    def page(self) -> Page:
        return self._page

    # ── Core: Send & Receive ────────────────────────────────────

    async def send_message(
        self,
        text: str,
        image_paths: list[str] | None = None,
        file_paths: list[str] | None = None,
        model: str | None = None,
    ) -> ChatResponse:
        """
        Send a message to ChatGPT and wait for the complete response.

        Args:
            text: The message text to send.
            image_paths: Optional list of local file paths to images to attach.
            file_paths: Optional list of local file paths to non-image files (PDF, etc.).

        Steps:
        1. Simulate thinking pause
        2. Upload images if provided
        3. Find and focus chat input
        4. Type message with human-like delays
        5. Click send
        6. Wait for response to complete
        7. Extract and return the response

        Returns ChatResponse with the assistant's reply and metadata.
        """
        all_attachments = (image_paths or []) + (file_paths or [])
        log.info(f"Sending message ({len(text)} chars, {len(all_attachments)} attachments): {text[:80]}...")
        start_time = time.time()

        # 0. Count existing assistant messages so we know when a new one appears
        pre_count = await count_assistant_messages(self._page)
        pre_turn_signature = await get_latest_assistant_turn_signature(self._page)
        log.debug(f"Assistant messages before send: {pre_count}")
        log.debug(f"Latest assistant turn before send: {pre_turn_signature}")

        # 1. Switch model if requested before interacting with the composer
        if model:
            await self.ensure_model(model)

        # 2. Brief pause (human would take a moment to start typing)
        await random_delay(250, 700)

        # 2.5. Upload files/images if provided
        if all_attachments:
            await self._upload_files(all_attachments)

        # 2. Find the chat input
        input_selector = await self._find_selector(Selectors.CHAT_INPUT, "chat input")
        if not input_selector:
            raise RuntimeError("Could not find chat input element")

        # 3. Paste the message (all at once)
        await human_type(self._page, input_selector, text)

        # Small pause after pasting (like a human reviewing before send)
        await random_delay(300, 600)

        # 4. Send the message
        sent = await self._click_send()
        if not sent:
            # Fallback: try pressing Enter
            log.info("Send button not found, trying Enter key")
            await self._page.keyboard.press("Enter")

        # 5. Wait for response with message count awareness
        log.info("Waiting for ChatGPT response...")
        expected_count = pre_count + 1
        completed = await wait_for_response_complete(
            self._page,
            expected_msg_count=expected_count,
            previous_turn_signature=pre_turn_signature,
        )

        if not completed:
            log.warning("Response may not be complete (timeout)")

        # Small buffer after completion to let DOM settle
        await asyncio.sleep(1.0)

        # 6. Check for generated images in the response FIRST
        #    (image turns have no copy button, so we must detect images
        #    before trying copy-button extraction)
        images = await extract_images_from_response(self._page)
        has_images = len(images) > 0

        # 7. Extract text content
        if has_images:
            # Image responses don't have a copy button — extract text
            # from the turn's DOM instead (will get the image title/desc)
            response_text = await self._extract_image_turn_text(pre_turn_signature)
            log.info(f"Response contains {len(images)} generated image(s)")
            for img in images:
                log.info(f"  Image: {img.alt or img.prompt_title} → {img.local_path}")
        else:
            # Standard text response — use copy button (most reliable)
            response_text = await extract_last_response_via_copy(
                self._page,
                previous_turn_signature=pre_turn_signature,
            )

            # ChatGPT can briefly expose status text like "thinking" as a turn.
            # Retry against the same new turn before giving that transient text back.
            if is_incomplete_response_text(response_text):
                log.warning("Extracted text looks incomplete/transient; retrying for final answer")
                for attempt in range(1, 3):
                    await asyncio.sleep(4)
                    await wait_for_response_complete(
                        self._page,
                        timeout_ms=90000,
                        previous_turn_signature=pre_turn_signature,
                    )
                    retry_text = await extract_last_response_via_copy(
                        self._page,
                        previous_turn_signature=pre_turn_signature,
                    )

                    if retry_text and not is_incomplete_response_text(retry_text):
                        response_text = retry_text
                        log.info(f"Recovered final response text on retry {attempt}")
                        break

                    if retry_text:
                        response_text = retry_text
                    log.warning(f"Retry {attempt} still incomplete/transient")

        elapsed_ms = int((time.time() - start_time) * 1000)
        thread_id = self._extract_thread_id()

        log.info(
            f"Response received ({elapsed_ms}ms, {len(response_text)} chars"
            f"{f', {len(images)} images' if has_images else ''}): "
            f"{response_text[:80]}..."
        )

        return ChatResponse(
            message=response_text,
            thread_id=thread_id,
            response_time_ms=elapsed_ms,
            images=images,
            has_images=has_images,
        )

    async def ensure_model(self, requested_model: str) -> None:
        """Switch ChatGPT's model picker to the requested model when possible."""
        target = resolve_requested_model(requested_model)
        if target is None:
            log.debug(f"No explicit browser model switch needed for request model={requested_model!r}")
            return

        current_label = await self._detect_current_model_label()
        if current_label and normalize_model_token(current_label) == normalize_model_token(target.ui_label):
            self._last_model_label = target.ui_label
            log.debug(f"ChatGPT model already selected: {target.ui_label}")
            return

        log.info(
            "Switching ChatGPT model: request=%s target=%s current=%s",
            requested_model,
            target.ui_label,
            current_label or self._last_model_label or "unknown",
        )

        opened = await self._open_model_picker(target.ui_label, current_label=current_label)
        if not opened:
            raise RuntimeError(f"Could not open ChatGPT model picker for '{target.ui_label}'")

        await asyncio.sleep(0.4)

        switched = await self._click_model_option(target.ui_label)
        if not switched:
            more_models_opened = await self._click_menu_text("More models")
            if more_models_opened:
                await asyncio.sleep(0.3)
                switched = await self._click_model_option(target.ui_label)

        if not switched:
            raise RuntimeError(f"Could not find ChatGPT model option '{target.ui_label}' in the model picker")

        confirmed = await self._wait_for_model_label(target.ui_label)
        if not confirmed:
            current_after = await self._detect_current_model_label()
            if normalize_model_token(current_after) != normalize_model_token(target.ui_label):
                raise RuntimeError(f"Model switch to '{target.ui_label}' could not be confirmed")

        self._last_model_label = target.ui_label
        log.info(f"Model switched to {target.ui_label}")

    # ── Navigation ──────────────────────────────────────────────

    async def new_chat(self) -> None:
        """Start a new conversation by navigating to the home page."""
        log.info("Starting new chat...")
        # Direct navigation is the most reliable way — avoids duplicate button issues
        await self._page.goto(Config.CHATGPT_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Wait for the chat input to be visible (signals page is ready)
        for selector in Selectors.CHAT_INPUT:
            try:
                await self._page.wait_for_selector(selector, timeout=10000, state="visible")
                log.debug(f"Chat input ready: {selector}")
                break
            except Exception:
                continue

        await random_delay(500, 1000)
        log.info("New chat started (navigated to home)")

    async def navigate_to_thread(self, thread_id: str) -> None:
        """Navigate to an existing conversation thread."""
        url = f"{Config.CHATGPT_URL}/c/{thread_id}"
        log.info(f"Navigating to thread: {thread_id}")
        await self._page.goto(url, wait_until="domcontentloaded")
        await random_delay(1500, 3000)
        log.info(f"Thread {thread_id} loaded")

    async def get_current_thread_url(self) -> str:
        """Get the current page URL (contains thread ID if in a conversation)."""
        return self._page.url

    # ── Sidebar ─────────────────────────────────────────────────

    async def list_threads(self) -> list[dict]:
        """
        Scrape the sidebar for recent conversation threads.

        Returns a list of dicts: [{id, title, url}, ...]
        """
        threads = []
        for selector in Selectors.SIDEBAR_THREAD_LINKS:
            try:
                elements = await self._page.query_selector_all(selector)
                for el in elements:
                    href = await el.get_attribute("href") or ""
                    title = (await el.inner_text()).strip()
                    match = re.search(r"/c/([a-f0-9-]+)", href)
                    if match:
                        threads.append({
                            "id": match.group(1),
                            "title": title,
                            "url": f"{Config.CHATGPT_URL}{href}",
                        })
                if threads:
                    break
            except Exception as e:
                log.debug(f"Sidebar scrape with {selector} failed: {e}")

        log.info(f"Found {len(threads)} threads in sidebar")
        return threads

    # ── Private Helpers ─────────────────────────────────────────

    async def _extract_image_turn_text(self, previous_turn_signature: str | None = None) -> str:
        """
        Extract any text content from the latest turn (for image responses).

        Image turns may contain a title/description like:
        "Creating image • Adorable orange tabby kitten close-up"
        """
        text = await self._page.evaluate(r"""
            (previousSignature) => {
                const articles = Array.from(document.querySelectorAll('article'));
                if (articles.length === 0) return '';

                const hasGeneratedImage = (article) => {
                    if (article.querySelector('img[alt="Generated image"], div[id^="image-"]')) return true;
                    for (const img of article.querySelectorAll('img')) {
                        const w = img.naturalWidth || img.width || 0;
                        const src = img.src || '';
                        if (w > 200 && (src.includes('backend-api/estuary') || src.includes('chatgpt.com'))) {
                            return true;
                        }
                    }
                    return false;
                };

                const isAssistantArticle = (article) => {
                    const hasAssistantRole = article.querySelector('[data-message-author-role="assistant"]');
                    const hasAgentTurn = article.querySelector('.agent-turn');
                    return Boolean(hasAssistantRole || hasAgentTurn || hasGeneratedImage(article));
                };

                let last = null;
                for (let idx = articles.length - 1; idx >= 0; idx--) {
                    const article = articles[idx];
                    if (!isAssistantArticle(article)) continue;

                    const stableId =
                        article.getAttribute('data-message-id') ||
                        article.getAttribute('data-testid') ||
                        article.id ||
                        '';
                    const signature = `${idx}:${stableId}`;
                    if (previousSignature && signature === previousSignature) {
                        return '';
                    }

                    last = article;
                    break;
                }

                if (!last) return '';

                // Try to get descriptive text (not "ChatGPT said:" heading)
                const spans = last.querySelectorAll('span');
                const parts = [];
                for (const span of spans) {
                    const t = (span.innerText || '').trim();
                    if (t && t.length > 3 && t.length < 300 &&
                        !t.includes('ChatGPT') && !t.includes('said')) {
                        parts.push(t);
                    }
                }
                if (parts.length > 0) return parts.join(' ');

                // Fallback: full turn inner text
                const full = (last.innerText || '').trim();
                // Strip the "ChatGPT said:" prefix
                return full.replace(/^ChatGPT said:\s*/i, '').trim();
            }
        """, previous_turn_signature)
        return text or ""

    async def _find_selector(self, selectors: list[str], name: str) -> str | None:
        """
        Try each selector in the fallback list. Return the first one that matches.
        """
        for selector in selectors:
            try:
                el = await self._page.wait_for_selector(
                    selector,
                    timeout=Config.SELECTOR_TIMEOUT,
                    state="visible",
                )
                if el:
                    log.debug(f"Found {name} via: {selector}")
                    return selector
            except Exception:
                log.debug(f"Selector miss for {name}: {selector}")
                continue

        log.warning(f"No working selector found for: {name}")
        return None

    async def _click_send(self) -> bool:
        """Try to click the send button using selector fallbacks."""
        selector = await self._find_selector(Selectors.SEND_BUTTON, "send button")
        if selector:
            await human_click(self._page, selector)
            log.debug("Send button clicked")
            return True
        return False

    async def _detect_current_model_label(self) -> str:
        """Best-effort detection of the currently selected ChatGPT model label."""
        known_labels = [option.ui_label for option in list_switchable_models()]
        if self._last_model_label and self._last_model_label not in known_labels:
            known_labels.append(self._last_model_label)
        if not known_labels:
            return ""

        label = await self._page.evaluate(
            r"""
            (knownLabels) => {
                const normalize = (value) =>
                    (value || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
                const isVisible = (el) => {
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 &&
                        rect.height > 0 &&
                        style.visibility !== "hidden" &&
                        style.display !== "none";
                };
                const wanted = (knownLabels || []).map((label) => ({
                    label,
                    normalized: normalize(label),
                })).filter((item) => item.normalized);
                const clickable = Array.from(document.querySelectorAll("button,[role='button'],[role='tab']"));
                const matches = [];
                for (const el of clickable) {
                    if (!isVisible(el)) continue;
                    const rect = el.getBoundingClientRect();
                    const primaryText = ((el.innerText || el.textContent || "")
                        .split(/\n+/)
                        .map((part) => part.trim())
                        .filter(Boolean)[0] || "").trim();
                    const rawText = [
                        primaryText,
                        el.innerText || "",
                        el.textContent || "",
                        el.getAttribute("aria-label") || "",
                        el.getAttribute("title") || "",
                    ].join(" ").trim();
                    const normalizedText = normalize(rawText);
                    const normalizedPrimary = normalize(primaryText);
                    if (!normalizedText) continue;
                    for (const wantedLabel of wanted) {
                        if (!normalizedText.includes(wantedLabel.normalized)) continue;
                        let score = 0;
                        if (normalizedPrimary === wantedLabel.normalized) score += 70;
                        else if (normalizedText === wantedLabel.normalized) score += 50;
                        else if (normalizedPrimary.startsWith(wantedLabel.normalized)) score += 35;
                        else if (normalizedText.startsWith(wantedLabel.normalized)) score += 25;
                        else score += 10;
                        score += Math.min(10, wantedLabel.normalized.length);
                        if (rect.top < 260) score += 20;
                        if (rect.left < 500) score += 10;
                        matches.push({
                            label: wantedLabel.label,
                            score,
                            top: rect.top,
                            left: rect.left,
                        });
                    }
                }
                matches.sort((a, b) => b.score - a.score || a.top - b.top || a.left - b.left);
                return matches.length ? matches[0].label : "";
            }
            """,
            known_labels,
        )
        return (label or "").strip()

    async def _open_model_picker(self, target_label: str, current_label: str = "") -> bool:
        """Open ChatGPT's model picker using the visible current-model button."""
        for selector in Selectors.MODEL_PICKER_BUTTON:
            try:
                el = await self._page.wait_for_selector(selector, timeout=1000, state="visible")
                if el:
                    await human_click(self._page, selector)
                    return True
            except Exception:
                continue

        hints = [current_label, self._last_model_label, target_label, "model", "GPT", "o3", "o4"]
        if await self._click_top_button_by_text(hints):
            return True

        return False

    async def _click_top_button_by_text(self, hints: list[str]) -> bool:
        """Click a visible top-of-page button whose label best matches the hints."""
        filtered_hints = [hint for hint in hints if (hint or "").strip()]
        if not filtered_hints:
            return False

        clicked = await self._page.evaluate(
            r"""
            (hints) => {
                const normalize = (value) =>
                    (value || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
                const wanted = (hints || []).map(normalize).filter(Boolean);
                const isVisible = (el) => {
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 &&
                        rect.height > 0 &&
                        style.visibility !== "hidden" &&
                        style.display !== "none";
                };
                const clickable = Array.from(document.querySelectorAll("button,[role='button'],[role='tab']"));
                const matches = [];
                for (const el of clickable) {
                    if (!isVisible(el)) continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.top > 320) continue;
                    const primaryText = ((el.innerText || el.textContent || "")
                        .split(/\n+/)
                        .map((part) => part.trim())
                        .filter(Boolean)[0] || "").trim();
                    const text = [
                        primaryText,
                        el.innerText || "",
                        el.textContent || "",
                        el.getAttribute("aria-label") || "",
                        el.getAttribute("title") || "",
                    ].join(" ").trim();
                    const normalizedText = normalize(text);
                    const normalizedPrimary = normalize(primaryText);
                    if (!normalizedText) continue;
                    let score = 0;
                    for (const hint of wanted) {
                        if (!normalizedText.includes(hint)) continue;
                        score = Math.max(
                            score,
                            normalizedPrimary === hint
                                ? 70
                                : normalizedText === hint
                                  ? 60
                                  : normalizedPrimary.startsWith(hint)
                                    ? 45
                                    : normalizedText.startsWith(hint)
                                      ? 40
                                      : 20,
                        );
                    }
                    if (!score) continue;
                    if (rect.left < 500) score += 10;
                    matches.push({ el, score, top: rect.top, left: rect.left });
                }
                matches.sort((a, b) => b.score - a.score || a.top - b.top || a.left - b.left);
                const best = matches[0];
                if (!best) return false;
                best.el.click();
                return true;
            }
            """,
            filtered_hints,
        )
        return bool(clicked)

    async def _click_model_option(self, target_label: str) -> bool:
        """Click a visible model option in an open picker/menu by its label."""
        return await self._click_menu_text(target_label)

    async def _click_menu_text(self, target_text: str) -> bool:
        """Click a visible menu-style element whose text matches the target."""
        clicked = await self._page.evaluate(
            r"""
            (targetText) => {
                const normalize = (value) =>
                    (value || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
                const target = normalize(targetText);
                if (!target) return false;
                const isVisible = (el) => {
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 &&
                        rect.height > 0 &&
                        style.visibility !== "hidden" &&
                        style.display !== "none";
                };
                const selectors = [
                    "[role='menuitemradio']",
                    "[role='menuitem']",
                    "[role='option']",
                    "button",
                    "[data-radix-collection-item]",
                    "li",
                ];
                const matches = [];
                for (const selector of selectors) {
                    for (const el of document.querySelectorAll(selector)) {
                        if (!isVisible(el)) continue;
                        const primaryText = ((el.innerText || el.textContent || "")
                            .split(/\n+/)
                            .map((part) => part.trim())
                            .filter(Boolean)[0] || "").trim();
                        const text = [
                            primaryText,
                            el.innerText || "",
                            el.textContent || "",
                            el.getAttribute("aria-label") || "",
                            el.getAttribute("title") || "",
                        ].join(" ").trim();
                        const normalizedText = normalize(text);
                        const normalizedPrimary = normalize(primaryText);
                        if (!normalizedText || !normalizedText.includes(target)) continue;
                        let score = 0;
                        if (normalizedPrimary === target) score += 80;
                        else if (normalizedText === target) score += 60;
                        else if (normalizedPrimary.startsWith(target)) score += 45;
                        else if (normalizedText.startsWith(target)) score += 40;
                        else score += 20;
                        const rect = el.getBoundingClientRect();
                        if (rect.top < 700) score += 10;
                        matches.push({ el, score, top: rect.top, left: rect.left });
                    }
                }
                matches.sort((a, b) => b.score - a.score || a.top - b.top || a.left - b.left);
                const best = matches[0];
                if (!best) return false;
                best.el.click();
                return true;
            }
            """,
            target_text,
        )
        return bool(clicked)

    async def _wait_for_model_label(self, target_label: str) -> bool:
        """Wait briefly until the current-model button reflects the requested label."""
        deadline = time.time() + (Config.CHATGPT_MODEL_SWITCH_TIMEOUT / 1000.0)
        target_normalized = normalize_model_token(target_label)
        while time.time() < deadline:
            current_label = await self._detect_current_model_label()
            if normalize_model_token(current_label) == target_normalized:
                return True
            await asyncio.sleep(0.25)
        return False

    async def _upload_files(self, file_paths: list[str]) -> None:
        """
        Upload files (images, PDFs, docs, etc.) to ChatGPT's input area.

        ChatGPT has a hidden <input type="file"> that accepts various file types.
        We set files on it directly (like drag-and-drop / file picker).
        """
        from pathlib import Path

        valid_paths = []
        for p in file_paths:
            path = Path(p)
            if path.exists() and path.is_file():
                valid_paths.append(str(path.resolve()))
            else:
                log.warning(f"File not found, skipping: {p}")

        if not valid_paths:
            log.warning("No valid files to upload")
            return

        log.info(f"Uploading {len(valid_paths)} file(s)...")

        # Find the file input element — ChatGPT has a hidden <input type="file">
        file_input = None
        for selector in Selectors.FILE_UPLOAD_INPUT:
            try:
                elements = await self._page.query_selector_all(selector)
                if elements:
                    file_input = elements[0]
                    log.debug(f"Found file input: {selector}")
                    break
            except Exception:
                continue

        if file_input:
            # Set files directly on the input element
            await file_input.set_input_files(valid_paths)
            log.info(f"Set {len(valid_paths)} file(s) on file input")
        else:
            # Fallback: use page.set_input_files with a broad selector
            log.info("No file input found via selectors, trying broad input[type=file]")
            try:
                await self._page.set_input_files("input[type='file']", valid_paths)
                log.info(f"Set {len(valid_paths)} file(s) via broad selector")
            except Exception as e:
                log.error(f"Failed to upload files: {e}")
                raise RuntimeError(f"Could not upload files: {e}")

        # Wait for files to be processed/attached (thumbnails/badges appear)
        await asyncio.sleep(3)
        # Additional wait if multiple files
        if len(valid_paths) > 1:
            await asyncio.sleep(len(valid_paths))
        log.info("File upload complete")

    def _extract_thread_id(self) -> str:
        """Extract the thread/conversation ID from the current URL."""
        url = self._page.url
        match = re.search(r"/c/([a-f0-9-]+)", url)
        return match.group(1) if match else ""
