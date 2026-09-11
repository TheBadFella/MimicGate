"""
Response completion detector for Google Gemini (gemini.google.com).

Detection strategy:
1. Detect completion using Stop-button disappearance and Copy-button appearance on <model-response>.
2. Extract text using the action-bar Copy button (lossless markdown), with DOM query as fallback.
3. Support polling and streaming deltas.
"""

from __future__ import annotations

import asyncio
import re

from patchright.async_api import Page

from src.browser.human import idle_mouse_movement
from src.gemini.selectors import GeminiSelectors
from src.log import setup_logging
from src.config import Config

log = setup_logging("gemini_detector")

# Shared DOM helpers: pick the turn action-bar Copy button, never a code-cell Copy.
_GEMINI_TURN_COPY_HELPERS_JS = r"""
    const textOf = (el) => ((el && (el.innerText || el.textContent)) || "").trim();
    const isVisible = (el) => {
        if (!el) return false;
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return rect.width > 0 &&
            rect.height > 0 &&
            style.visibility !== "hidden" &&
            style.display !== "none";
    };
    const isSnippetCopyButton = (el) => {
        if (!el) return false;
        const label = [
            el.getAttribute("aria-label") || "",
            el.getAttribute("title") || "",
            textOf(el).slice(0, 80)
        ].join(" ").toLowerCase();
        if (label.includes("copy code") || label.includes("copy prompt") || label.includes("copy table")) {
            return true;
        }
        return Boolean(el.closest("pre, code, code-block, .code-block, syntax-highlighter"));
    };
    const findTurnCopyButton = (root) => {
        if (!root) return null;
        const matches = Array.from(root.querySelectorAll(
            'button[aria-label*="Copy response" i], button[aria-label="Copy" i], button[aria-label*="Copy" i], button:has(mat-icon[data-mat-icon-name="content_copy"])'
        )).filter((el) => !isSnippetCopyButton(el));
        const preferred = matches.find((el) => /copy response/i.test(el.getAttribute("aria-label") || ""));
        if (preferred) return preferred;
        const visible = matches.filter(isVisible);
        if (visible.length) return visible[visible.length - 1];
        return matches.length ? matches[matches.length - 1] : null;
    };
    const turnSignature = (turns, last) => {
        const text = last && last.innerText ? last.innerText.trim().slice(0, 80) : "";
        return `${turns.length - 1}:${text}`;
    };
"""

_CLICK_GEMINI_TURN_COPY_JS = r"""
(previousSignature) => {
""" + _GEMINI_TURN_COPY_HELPERS_JS + r"""
    const turns = Array.from(document.querySelectorAll('model-response, div.response-container'));
    if (turns.length === 0) return { clicked: false, reason: "no-turns" };
    const last = turns[turns.length - 1];
    const signature = turnSignature(turns, last);
    if (previousSignature && signature === previousSignature) {
        return { clicked: false, reason: "same-turn", signature };
    }
    const copyBtn = findTurnCopyButton(last);
    if (!copyBtn) return { clicked: false, reason: "no-turn-copy", signature };
    copyBtn.click();
    return { clicked: true, reason: "ok", signature };
}
"""

_LATEST_TURN_SNAPSHOT_JS = r"""
() => {
""" + _GEMINI_TURN_COPY_HELPERS_JS + r"""
    const turns = Array.from(document.querySelectorAll('model-response, div.response-container'));
    const hasStopButton = Boolean(document.querySelector('button[aria-label*="Stop" i], .stop-button'));
    if (turns.length === 0) {
        return {
            found: false,
            index: -1,
            signature: null,
            hasCopyButton: false,
            hasStopButton,
            text: '',
        };
    }
    const idx = turns.length - 1;
    const last = turns[idx];
    const text = last.innerText ? last.innerText.trim() : '';
    return {
        found: true,
        index: idx,
        signature: turnSignature(turns, last),
        hasCopyButton: Boolean(findTurnCopyButton(last)),
        hasStopButton,
        text,
    };
}
"""

_DOM_EXTRACT_JS = r"""
() => {
    const turns = Array.from(document.querySelectorAll('model-response, div.response-container'));
    if (turns.length === 0) return '';
    const last = turns[turns.length - 1];
    const content = last.querySelector('message-content, markdown, .markdown, .model-response-text');
    const source = content || last;
    const clone = source.cloneNode(true);
    clone.querySelectorAll('code-block, pre, .code-block, syntax-highlighter').forEach((el) => el.remove());
    const stripped = (clone.innerText || '').trim();
    if (stripped) return stripped;
    return (source.innerText || last.innerText || '').trim();
}
"""


def normalize_assistant_text(text: str | None) -> str:
    """Normalize extracted assistant text for validation and comparisons."""
    return (text or "").strip()


def is_incomplete_response_text(text: str | None) -> bool:
    """Heuristic: true when text looks like transient thinking/analyzing status."""
    cleaned = normalize_assistant_text(text)
    if not cleaned:
        return True

    lower = cleaned.lower()
    markers = [
        "thinking",
        "generating",
        "working on",
        "please wait",
        "searching",
    ]

    if any(marker in lower for marker in markers):
        if len(cleaned) < 160:
            return True
        if lower.startswith(tuple(markers)):
            return True

    return False


async def count_assistant_messages(page: Page) -> int:
    """Count how many assistant responses currently exist on the page."""
    try:
        return await page.evaluate(
            """
            () => {
                const turns = document.querySelectorAll('model-response, div.response-container');
                return turns.length;
            }
            """
        )
    except Exception as e:
        log.warning(f"Failed to count assistant messages: {e}")
        return 0


async def get_latest_assistant_turn_signature(page: Page) -> str | None:
    """Return a unique signature string for the latest assistant message turn."""
    try:
        return await page.evaluate(
            """
            () => {
                const turns = Array.from(document.querySelectorAll('model-response, div.response-container'));
                if (turns.length === 0) return null;
                const last = turns[turns.length - 1];
                const text = last.innerText ? last.innerText.trim().slice(0, 80) : '';
                return `${turns.length - 1}:${text}`;
            }
            """
        )
    except Exception as e:
        log.debug(f"Failed to get latest assistant turn signature: {e}")
        return None


async def _latest_assistant_turn_snapshot(page: Page) -> dict:
    """Return metadata snapshot for the latest assistant turn in Gemini."""
    try:
        return await page.evaluate(_LATEST_TURN_SNAPSHOT_JS)
    except Exception as e:
        log.debug(f"Failed to snapshot latest assistant turn: {e}")
        return {
            "found": False,
            "index": -1,
            "signature": None,
            "hasCopyButton": False,
            "hasStopButton": False,
            "text": "",
        }


async def wait_for_response_complete(
    page: Page,
    expected_msg_count: int | None = None,
    previous_turn_signature: str | None = None,
    timeout_ms: int = 120000,
    poll_interval_ms: int = 400,
) -> bool:
    """
    Wait until Gemini finishes responding.

    Stages:
    1. Wait for generation to start (new turn or stop button visible).
    2. Wait for stop button to disappear and copy button or text stability.
    """
    poll_interval = poll_interval_ms / 1000
    elapsed = 0.0

    log.info("Waiting for Gemini response generation to start...")
    start_detected = False
    start_wait_max = 25.0

    while elapsed < start_wait_max:
        snapshot = await _latest_assistant_turn_snapshot(page)
        curr_count = await count_assistant_messages(page)

        new_turn_appeared = (
            expected_msg_count is not None and curr_count >= expected_msg_count
        ) or (
            previous_turn_signature is not None
            and snapshot["signature"] is not None
            and snapshot["signature"] != previous_turn_signature
        )

        if snapshot["hasStopButton"] or new_turn_appeared:
            start_detected = True
            log.info(f"Response generation started after {elapsed:.1f}s")
            break

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    if not start_detected:
        log.warning("No response generation detected within start window; proceeding to completion check")

    # Now wait for generation to complete
    log.info("Waiting for response generation to complete...")
    stable_count = 0
    required_stable = 3
    last_text = ""

    while (elapsed * 1000) < timeout_ms:
        snapshot = await _latest_assistant_turn_snapshot(page)

        # Periodic mouse movement to simulate human activity
        if int(elapsed * 10) % 20 == 0:
            try:
                await idle_mouse_movement(page)
            except Exception:
                pass

        if not snapshot["hasStopButton"]:
            is_new = previous_turn_signature is None or snapshot["signature"] != previous_turn_signature
            if not is_new:
                stable_count = 0
                last_text = ""
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                continue

            # If a turn-level copy button is present on the new turn, it is complete
            if snapshot["hasCopyButton"]:
                log.info(f"Response completed: copy button found on turn after {elapsed:.1f}s")
                return True

            current_text = snapshot["text"]
            if current_text and current_text == last_text:
                stable_count += 1
                if stable_count >= required_stable:
                    if not is_incomplete_response_text(current_text):
                        log.info(f"Response completed: text stable after {elapsed:.1f}s")
                        return True
            else:
                stable_count = 0
                last_text = current_text

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    log.warning(f"Timed out waiting for Gemini response after {elapsed:.1f}s")
    return False


async def extract_last_response_via_copy(
    page: Page,
    previous_turn_signature: str | None = None,
) -> str:
    """
    Extract the latest assistant response by clicking the native turn Copy button.
    Skips code-block Copy buttons and previous-turn copies. Falls back to DOM text.
    """
    log.debug("Attempting extraction via Gemini copy button...")

    try:
        snapshot = await _latest_assistant_turn_snapshot(page)
        if (
            previous_turn_signature
            and snapshot.get("signature") == previous_turn_signature
        ):
            log.warning("Latest Gemini turn is unchanged; skipping copy of previous response")
            return ""

        await page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        await page.evaluate("navigator.clipboard.writeText('').catch(() => {})")

        click_result = await page.evaluate(_CLICK_GEMINI_TURN_COPY_JS, previous_turn_signature)
        clicked = isinstance(click_result, dict) and click_result.get("clicked")

        if clicked:
            for _ in range(10):
                await asyncio.sleep(0.2)
                text = await page.evaluate("navigator.clipboard.readText().catch(() => '')")
                if text and text.strip():
                    log.info(f"Successfully extracted {len(text)} chars via Copy button")
                    return text.strip()
        elif isinstance(click_result, dict):
            log.debug("Gemini turn copy click not used: %s", click_result.get("reason"))

    except Exception as e:
        log.warning(f"Copy extraction failed ({e}), falling back to DOM extraction")

    return await extract_last_response_via_dom(page, previous_turn_signature=previous_turn_signature)


async def extract_last_response_via_dom(
    page: Page,
    previous_turn_signature: str | None = None,
) -> str:
    """Extract assistant response text directly from DOM elements."""
    log.debug("Extracting response text via DOM queries...")
    try:
        snapshot = await _latest_assistant_turn_snapshot(page)
        if (
            previous_turn_signature
            and snapshot.get("signature") == previous_turn_signature
        ):
            return ""
        text = await page.evaluate(_DOM_EXTRACT_JS)
        return (text or "").strip()
    except Exception as e:
        log.error(f"Failed to extract response via DOM: {e}")
        return ""
