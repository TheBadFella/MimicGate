"""
Google Gemini client -- core interaction logic for gemini.google.com.

Sends messages, waits for responses, switches models, and manages conversations.
Adheres to the same interface as ChatGPTClient and ClaudeClient for provider polymorphism.
"""

from __future__ import annotations

import asyncio
import copy
import os
import re
import tempfile
import time
from pathlib import Path
from typing import AsyncGenerator

from patchright.async_api import Page

from src.browser.human import human_type, human_click, random_delay
from src.chatgpt.models import ChatResponse
from src.config import Config
from src.gemini.detector import (
    count_assistant_messages,
    extract_last_response_via_copy,
    get_latest_assistant_turn_signature,
    is_incomplete_response_text,
    wait_for_response_complete,
)
from src.gemini.model_registry import (
    GeminiModelOption,
    normalize_token,
    resolve_gemini_model,
)
from src.gemini.selectors import GeminiSelectors
from src.log import setup_logging

log = setup_logging("gemini_client")


class GeminiClient:
    """
    High-level client for interacting with the Google Gemini web interface.

    Requires a Playwright/Patchright Page authenticated and loaded on gemini.google.com.
    """

    def __init__(self, page: Page) -> None:
        self._page = page
        self._attach_debug_listeners(page)

    def _attach_debug_listeners(self, page: Page) -> None:
        try:
            page.on("console", lambda msg: log.debug("GEMINI BROWSER CONSOLE [%s]: %s", msg.type, msg.text[:200]))
            page.on("requestfailed", lambda req: log.debug("GEMINI REQ FAILED: %s -> %s", req.url[:120], req.failure))
        except Exception:
            pass

    @property
    def page(self) -> Page:
        return self._page

    def bind_page(self, page: Page | None) -> GeminiClient:
        """Return a client bound to a specific tab without mutating this instance."""
        if page is None or page is self._page:
            return self
        bound = copy.copy(self)
        bound._page = page
        bound._attach_debug_listeners(page)
        return bound

    # -- Core: Send & Receive ------------------------------------

    async def send_message(
        self,
        text: str,
        image_paths: list[str] | None = None,
        file_paths: list[str] | None = None,
        read_aloud: bool = False,
        model: str | None = None,
    ) -> ChatResponse:
        """
        Send a message to Gemini and wait for the complete response.

        Args:
            text: Prompt text.
            image_paths: Optional local image file paths.
            file_paths: Optional local file paths.
            read_aloud: Accepted for API compatibility.
            model: Optional model name to switch to before sending.

        Returns ChatResponse with the reply and metadata.
        """
        all_attachments = (image_paths or []) + (file_paths or [])
        log.info(f"Sending message to Gemini ({len(text)} chars, {len(all_attachments)} attachments): {text[:80]}...")
        start_time = time.time()
        if self._page.is_closed():
            context = getattr(self._page, "context", None)
            if context and getattr(context, "pages", None):
                for p in context.pages:
                    if not p.is_closed():
                        log.warning("GeminiClient page was closed; recovered active page from context")
                        self._page = p
                        self._attach_debug_listeners(p)
                        break
            if self._page.is_closed():
                raise RuntimeError("Gemini browser page is closed")

        # Switch model if requested
        if model:
            await self.switch_model(model)

        # 0. Count existing turns to detect new answer
        pre_count = await count_assistant_messages(self._page)
        pre_turn_signature = await get_latest_assistant_turn_signature(self._page)
        log.debug(f"Gemini turns before send: count={pre_count}, sig={pre_turn_signature}")

        await random_delay(200, 500)

        # 1. Find and focus the chat input
        input_selector = await self._find_selector(GeminiSelectors.CHAT_INPUT, "chat input")
        if not input_selector:
            raise RuntimeError("Could not find Gemini chat input element")

        # Click to focus the Quill editor
        try:
            await self._page.click(input_selector)
        except Exception:
            pass

        # Check for long prompt fallback
        submitted_text = text
        if (
            Config.GEMINI_LONG_PROMPT_THRESHOLD > 0
            and len(text) >= Config.GEMINI_LONG_PROMPT_THRESHOLD
            and Config.GEMINI_LONG_PROMPT_FALLBACK == "attachment"
        ):
            temporary_prompt_path = self._create_prompt_attachment(text)
            attachment_name = Path(temporary_prompt_path).name
            submitted_text = (
                f"Read the attached file `{attachment_name}` as the complete user request. "
                "Follow its instructions exactly and use all of its content before answering."
            )
            log.info(
                "Prompt is too long for the Gemini composer (%d chars); using attachment fallback (%s)",
                len(text),
                attachment_name,
            )
            all_attachments = [*all_attachments, temporary_prompt_path]

        # 2. Type message
        await human_type(self._page, input_selector, submitted_text)

        # 3. Handle attachments if any
        if all_attachments:
            await self._upload_files(all_attachments)
            await self._wait_for_attachments_ready(timeout_s=120.0)

        await random_delay(150, 300)
        await random_delay(200, 400)

        # 4. Click Send or press Enter
        sent = await self._click_send()
        if not sent:
            log.info("Send button not found or not clickable; pressing Enter")
            await self._page.keyboard.press("Enter")
        # 4. Click Send
        if all_attachments:
            sent = await self._click_send(timeout_s=30.0)
            if not sent:
                raise RuntimeError("Failed to send message: attachment upload did not complete or send button was not ready")
        else:
            sent = await self._click_send(timeout_s=25.0)
            if not sent:
                log.info("Send button not found or not clickable; pressing Enter")
                await self._page.keyboard.press("Enter")

        # 5. Wait for response
        log.info("Waiting for Gemini response...")
        expected_count = pre_count + 1
        completed = await wait_for_response_complete(
            self._page,
            expected_msg_count=expected_count,
            previous_turn_signature=pre_turn_signature,
            timeout_ms=Config.RESPONSE_TIMEOUT,
        )

        if not completed:
            log.warning("Response may not be complete (timeout)")

        await asyncio.sleep(0.5)

        # 6. Extract response text
        response_text = await extract_last_response_via_copy(
            self._page,
            previous_turn_signature=pre_turn_signature,
        )

        # Retry if transient thinking marker captured
        if is_incomplete_response_text(response_text):
            log.warning("Extracted text looks transient; waiting for final answer")
            for attempt in range(1, 3):
                await asyncio.sleep(3)
                await wait_for_response_complete(
                    self._page,
                    timeout_ms=60000,
                    previous_turn_signature=pre_turn_signature,
                )
                retry_text = await extract_last_response_via_copy(
                    self._page,
                    previous_turn_signature=pre_turn_signature,
                )
                if retry_text and not is_incomplete_response_text(retry_text):
                    response_text = retry_text
                    log.info(f"Recovered response text on retry {attempt}")
                    break

        elapsed_ms = int((time.time() - start_time) * 1000)
        thread_id = self._extract_thread_id()

        log.info(f"Response received ({elapsed_ms}ms, {len(response_text)} chars): {response_text[:80]}...")

        return ChatResponse(
            message=response_text,
            thread_id=thread_id,
            response_time_ms=elapsed_ms,
            images=[],
            has_images=False,
            audio=None,
            has_audio=False,
        )

    # -- Model Switching -----------------------------------------

    async def get_current_model(self) -> str:
        """Return the label of the currently active model from the UI."""
        for selector in GeminiSelectors.CURRENT_MODEL_LABEL:
            try:
                el = await self._page.query_selector(selector)
                if el:
                    text = (await el.inner_text()).strip()
                    if text:
                        return text
            except Exception:
                continue
        return ""

    async def switch_model(self, model_request: str) -> bool:
        """
        Switch the model via Gemini'\''s mode switcher (<bard-mode-switcher>).
        Returns True if already on the model or successfully switched.
        """
        resolved: GeminiModelOption | None = resolve_gemini_model(model_request)
        if not resolved:
            log.debug(f"Model request '{model_request}' resolves to current browser model; no switch needed")
            return True

        current = await self.get_current_model()
        norm_current = normalize_token(current)

        # Check if already active
        for label in resolved.ui_labels:
            if normalize_token(label) in norm_current or norm_current in normalize_token(label):
                log.debug(f"Already on target model '{resolved.ui_label}' (UI shows '{current}')")
                return True

        log.info(f"Switching model from '{current}' to '{resolved.ui_label}'...")

        # 1. Click mode switcher button to open menu
        switcher_btn = await self._find_selector(GeminiSelectors.MODEL_SWITCHER_BUTTON, "mode switcher button")
        if not switcher_btn:
            log.warning("Could not find mode switcher button; skipping switch")
            return False

        await self._page.click(switcher_btn)
        await asyncio.sleep(0.5)

        # 2. Wait for menu panel to open
        for panel_sel in GeminiSelectors.MODEL_MENU_PANEL:
            try:
                await self._page.wait_for_selector(panel_sel, timeout=3000, state="visible")
                break
            except Exception:
                continue

        # 3. Find target menu item
        clicked = False
        target_tokens = [normalize_token(l) for l in resolved.ui_labels]

        try:
            items = await self._page.query_selector_all(", ".join(GeminiSelectors.MODEL_MENU_ITEMS))
            # Pass 1: exact match
            for item in items:
                item_text = (await item.inner_text()).strip()
                norm_item = normalize_token(item_text)
                for t in target_tokens:
                    if t and t in norm_item:
                        log.info(f"Clicking menu option: {item_text.splitlines()[0]}")
                    if t and t == norm_item:
                        log.info(f"Clicking menu option (exact): {item_text.splitlines()[0]}")
                        await item.click()
                        clicked = True
                        break
                if clicked:
                    break

            # Pass 2: token match with safety guards against partial collision
            if not clicked:
                for item in items:
                    item_text = (await item.inner_text()).strip()
                    norm_item = normalize_token(item_text)
                    # Don't match standard flash against lite
                    if "lite" in norm_item and not any("lite" in t for t in target_tokens):
                        continue
                    # Don't match pro against non-pro or vice-versa
                    if "pro" in norm_item and not any("pro" in t for t in target_tokens):
                        continue
                    for t in target_tokens:
                        if t and (t in norm_item or norm_item in t):
                            log.info(f"Clicking menu option (token): {item_text.splitlines()[0]}")
                            await item.click()
                            clicked = True
                            break
                    if clicked:
                        break
        except Exception as e:
            log.warning(f"Error clicking model item: {e}")

        if not clicked:
            log.warning(f"Could not find menu item for '{resolved.ui_label}'; closing menu")
            # Click outside to dismiss menu
            await self._page.keyboard.press("Escape")
            return False

        await asyncio.sleep(0.6)
        new_model = await self.get_current_model()
        log.info(f"Switched model. Active model is now: '{new_model}'")
        return True

    # -- Navigation & Thread Management --------------------------

    async def new_chat(self) -> None:
        """Start a new Gemini conversation."""
        log.info("Starting new Gemini chat...")
        target_url = (Config.GEMINI_URL or "https://gemini.google.com").rstrip("/") + "/app"
        base = (Config.GEMINI_URL or "https://gemini.google.com").rstrip("/")
        target_url = base if base.endswith("/app") else f"{base}/app"

        # If already on /app with empty conversation, avoid full reload
        try:
            current_url = self._page.url
            if "/app" in current_url and not re.search(r"/app/[a-zA-Z0-9_-]{5,}", current_url):
                assistant_turns = await count_assistant_messages(self._page)
                if assistant_turns == 0:
                    input_selector = await self._find_selector(GeminiSelectors.CHAT_INPUT, "chat input")
                    if input_selector:
                        try:
                            await self._page.evaluate(
                                "(sel) => { const el = document.querySelector(sel); if (el) el.innerHTML = '<p><br></p>'; }",
                                input_selector,
                            )
                        except Exception:
                            pass
                        log.info("Already on clean new chat page")
                        return
        except Exception:
            pass

        try:
            btn = await self._find_selector(GeminiSelectors.NEW_CHAT_BUTTON, "new chat button")
            if btn:
                await self._page.click(btn)
                await asyncio.sleep(1.0)
            else:
                await self._page.goto(target_url, wait_until="domcontentloaded")
        except Exception:
            await self._page.goto(target_url, wait_until="domcontentloaded")

        # Wait for chat input or detect error/login
        chat_ready = False
        for selector in GeminiSelectors.CHAT_INPUT:
            try:
                el = await self._page.wait_for_selector(selector, timeout=10000, state="visible")
                if el:
                    chat_ready = True
                    break
            except Exception:
                continue

        if not chat_ready:
            for selector in GeminiSelectors.ERROR_INDICATORS:
                try:
                    err_el = await self._page.query_selector(selector)
                    if err_el and await err_el.is_visible():
                        raise RuntimeError(
                            "Gemini returned 'Something went wrong' (p=no_access). "
                            "This Google account is not eligible or restricted for Gemini web app access."
                        )
                except Exception as e:
                    if "Gemini returned" in str(e):
                        raise
            for selector in GeminiSelectors.LOGIN_INDICATORS:
                try:
                    login_el = await self._page.query_selector(selector)
                    if login_el and await login_el.is_visible():
                        raise RuntimeError("Gemini is not logged in — sign in required.")
                except Exception as e:
                    if "Gemini is not logged in" in str(e):
                        raise
            raise RuntimeError("Could not find Gemini chat input element after navigation")

        await random_delay(200, 400)
        log.info("New chat ready")

    async def navigate_to_thread(self, thread_id: str) -> None:
        """Navigate to an existing Gemini conversation thread."""
        base = (Config.GEMINI_URL or "https://gemini.google.com").rstrip("/")
        url = f"{base}/app/{thread_id}"
        log.info(f"Navigating to Gemini thread: {thread_id}")
        await self._page.goto(url, wait_until="domcontentloaded")
        await random_delay(600, 1200)

    async def get_current_thread_url(self) -> str:
        return self._page.url

    async def list_threads(self) -> list[dict]:
        """Scrape recent chat history items from the sidebar."""
        threads = []
        for selector in GeminiSelectors.SIDEBAR_THREAD_LINKS:
            try:
                elements = await self._page.query_selector_all(selector)
                for el in elements:
                    href = await el.get_attribute("href")
                    title = (await el.inner_text()).strip()
                    if href:
                        match = re.search(r"/app/([a-zA-Z0-9_-]+)", href)
                        t_id = match.group(1) if match else href
                        threads.append({"id": t_id, "title": title, "url": href})
                if threads:
                    break
            except Exception:
                continue
        return threads

    # -- Internal Helpers ----------------------------------------

    async def _find_selector(self, selectors: list[str], description: str = "") -> str | None:
        for selector in selectors:
            try:
                el = await self._page.wait_for_selector(selector, timeout=1500, state="visible")
                if el:
                    return selector
            except Exception:
                continue
        return None

    async def _click_send(self, timeout_s: float = 20.0) -> bool:
        """Wait up to timeout_s for the send button to become visible and enabled, then click it."""
        start = time.monotonic()
        while time.monotonic() - start < timeout_s:
            for selector in GeminiSelectors.SEND_BUTTON:
                try:
                    el = await self._page.query_selector(selector)
                    if el and await el.is_visible():
                        is_disabled = (
                            await el.get_attribute("disabled") is not None
                            or await el.get_attribute("aria-disabled") == "true"
                        )
                        if not is_disabled:
                            await human_click(self._page, selector)
                            log.debug(f"Clicked send button: {selector}")
                            log.info(f"Clicked send button: {selector}")
                            return True
                except Exception:
                    continue
            await asyncio.sleep(0.5)
        return False

    async def _wait_for_attachments_ready(self, timeout_s: float = 120.0) -> bool:
        """
        Wait for attached files/images to finish uploading.
        Specifically, wait until the upload spinning wheel on the image preview disappears
        and the send button becomes active and enabled.
        """
        log.info("Waiting for Gemini attachment upload to complete (spinning wheel to finish)...")
        start = time.monotonic()

        # 1. First ensure attachment preview chip is in the DOM
        badge_selector = ", ".join(GeminiSelectors.ATTACHMENT_BADGE)
        try:
            await self._page.wait_for_selector(badge_selector, timeout=10000, state="attached")
            log.info("Attachment preview detected in composer")
        except Exception:
            log.warning("Attachment preview element was not detected within 10s")

        # 2. Give the UI a moment to show the in-flight upload spinner
        await asyncio.sleep(1.0)

        # 3. Poll until no upload spinner is visible
        spinner_selector = ", ".join(GeminiSelectors.ATTACHMENT_SPINNER)

        while time.monotonic() - start < timeout_s:
            is_spinning = False
            try:
                spinners = await self._page.query_selector_all(spinner_selector)
                for sp in spinners:
                    if await sp.is_visible():
                        is_spinning = True
                        break
            except Exception:
                pass

            if is_spinning:
                log.info("Gemini attachment upload in progress (spinning wheel active)...")
                await asyncio.sleep(1.0)
                continue

            # Check if send button is visible and enabled
            send_btn_ready = False
            for sel in GeminiSelectors.SEND_BUTTON:
                try:
                    btn = await self._page.query_selector(sel)
                    if btn and await btn.is_visible():
                        is_disabled = (
                            await btn.get_attribute("disabled") is not None
                            or await btn.get_attribute("aria-disabled") == "true"
                        )
                        if not is_disabled:
                            send_btn_ready = True
                            break
                except Exception:
                    continue

            if send_btn_ready:
                # Settle confirmation: ensure no spinner reappears
                await asyncio.sleep(1.0)
                recheck_spinning = False
                try:
                    spinners = await self._page.query_selector_all(spinner_selector)
                    for sp in spinners:
                        if await sp.is_visible():
                            recheck_spinning = True
                            break
                except Exception:
                    pass

                if not recheck_spinning:
                    log.info("Gemini attachment upload finished: spinning wheel completed and send button ready")
                    return True

            await asyncio.sleep(0.8)

        log.warning("Timed out waiting for Gemini attachment upload spinner to finish")
        return False

    async def _upload_files(self, file_paths: list[str]) -> None:
        """Upload file attachments via the file input element."""
        valid_paths = [str(Path(p).resolve()) for p in file_paths if os.path.exists(p)]
        if not valid_paths:
            log.warning("No valid files to upload")
            return

        log.info(f"Uploading {len(valid_paths)} attachment(s) to Gemini...")

        # 1. Try finding an existing file input element first
        file_input = None
        for selector in GeminiSelectors.FILE_UPLOAD_INPUT:
            try:
                elements = await self._page.query_selector_all(selector)
                if elements:
                    file_input = elements[0]
                    log.debug(f"Found file input: {selector}")
                    break
            except Exception:
                continue

        # 2. If not found, click the attach button to trigger menu and input injection
        if not file_input:
            for btn_sel in GeminiSelectors.ATTACH_BUTTON:
                try:
                    btn = await self._page.query_selector(btn_sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        await asyncio.sleep(0.6)
                        break
                except Exception as e:
                    log.debug(f"Could not click attach button {btn_sel}: {e}")

            # Re-check for file input now that menu was triggered
            for selector in GeminiSelectors.FILE_UPLOAD_INPUT:
                try:
                    elements = await self._page.query_selector_all(selector)
                    if elements:
                        file_input = elements[0]
                        log.debug(f"Found file input after opening menu: {selector}")
                        break
                except Exception:
                    continue

        if file_input:
            try:
                await file_input.set_input_files(valid_paths)
                log.info(f"Set {len(valid_paths)} file(s) on file input")
            except Exception as e:
                log.warning(f"Error setting input files: {e}")
        else:
            # Fallback: click Upload files menu item with expect_file_chooser
            for uploader_sel in GeminiSelectors.UPLOAD_FILES_MENU_BUTTON:
                try:
                    uploader_btn = await self._page.query_selector(uploader_sel)
                    if uploader_btn and await uploader_btn.is_visible():
                        async with self._page.expect_file_chooser(timeout=5000) as fc_info:
                            await uploader_btn.click()
                        file_chooser = await fc_info.value
                        await file_chooser.set_files(valid_paths)
                        log.info(f"Set {len(valid_paths)} file(s) via file chooser")
                        break
                except Exception as e:
                    log.debug(f"File chooser upload failed with {uploader_sel}: {e}")

        # Close any lingering menu by pressing Escape
        try:
            await self._page.keyboard.press("Escape")
        except Exception:
            pass

        # Wait for attachment badge or settle time
        badge_selector = ", ".join(GeminiSelectors.ATTACHMENT_BADGE)
        try:
            await self._page.wait_for_selector(badge_selector, timeout=8000, state="attached")
            log.info("Attachment badge detected in Gemini composer")
        except Exception:
            log.debug("Attachment badge wait timed out, using fallback sleep")
            await asyncio.sleep(2.0)
            if len(valid_paths) > 1:
                await asyncio.sleep(len(valid_paths))
        log.info("File upload dispatched to input element")

        # Wait for any in-flight upload spinner to complete
        spinner_selector = ", ".join(GeminiSelectors.ATTACHMENT_SPINNER)
        for _ in range(30):
            try:
                spinner = await self._page.query_selector(spinner_selector)
                if spinner and await spinner.is_visible():
                    log.debug("Waiting for Gemini attachment upload spinner to finish...")
                    await asyncio.sleep(1.0)
                else:
                    break
            except Exception:
                break

        log.info("File upload complete")

    def _extract_thread_id(self) -> str:
        """Extract conversation UUID / id from current URL."""
        match = re.search(r"/app/([a-zA-Z0-9_-]+)", self._page.url)
        return match.group(1) if match else ""

    @staticmethod
    def _create_prompt_attachment(text: str) -> str:
        """Persist a prompt as a UTF-8 temporary file for Gemini upload."""
        fd, filename = tempfile.mkstemp(
            prefix="catgpt-gemini-prompt-",
            suffix=".txt",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            Path(filename).unlink(missing_ok=True)
            raise
        return filename
