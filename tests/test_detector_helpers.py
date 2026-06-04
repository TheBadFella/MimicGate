from __future__ import annotations

import sys
import types
import unittest
import importlib.util
from pathlib import Path


if "patchright" not in sys.modules and importlib.util.find_spec("patchright.async_api") is None:
    patchright_mod = types.ModuleType("patchright")
    async_api_mod = types.ModuleType("patchright.async_api")
    async_api_mod.Page = object
    async_api_mod.BrowserContext = object
    async_api_mod.Playwright = object
    async_api_mod.Frame = object
    async_api_mod.Request = object
    async_api_mod.Response = object

    def _fake_async_playwright():
        return None

    async_api_mod.async_playwright = _fake_async_playwright
    sys.modules["patchright"] = patchright_mod
    sys.modules["patchright.async_api"] = async_api_mod

if "playwright_stealth" not in sys.modules:
    playwright_stealth_mod = types.ModuleType("playwright_stealth")

    class _FakeStealth:
        script_payload = ""

    playwright_stealth_mod.Stealth = _FakeStealth
    sys.modules["playwright_stealth"] = playwright_stealth_mod


from patchright.async_api import async_playwright

from src.chatgpt.detector import (
    _CLICK_LATEST_COPY_BUTTON_JS,
    is_incomplete_response_text,
    normalize_assistant_text,
)


class DetectorHelperTests(unittest.TestCase):
    def test_normalize_assistant_text_removes_heading(self) -> None:
        self.assertEqual(
            normalize_assistant_text("ChatGPT said:  final answer  "),
            "final answer",
        )

    def test_incomplete_response_text_detects_transient_status(self) -> None:
        self.assertTrue(is_incomplete_response_text("Pro thinking"))
        self.assertTrue(is_incomplete_response_text("Searching the web"))
        self.assertTrue(is_incomplete_response_text("Creating image"))
        self.assertTrue(is_incomplete_response_text("Generating image for your request"))
        self.assertFalse(is_incomplete_response_text("Here is the final answer with enough detail."))


class DetectorCopyButtonTests(unittest.IsolatedAsyncioTestCase):
    async def test_latest_turn_copy_ignores_code_block_copy_buttons(self) -> None:
        playwright_context = async_playwright()
        if playwright_context is None:
            self.skipTest("patchright is not installed")

        playwright = await playwright_context.__aenter__()
        chrome_path = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        launch_options = {"headless": True}
        if chrome_path.exists():
            launch_options["executable_path"] = str(chrome_path)

        try:
            browser = await playwright.chromium.launch(**launch_options)
        except Exception as exc:
            await playwright_context.__aexit__(None, None, None)
            self.skipTest(f"browser runtime is not available: {exc}")

        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_content(
                """
                <!doctype html>
                <main>
                  <article data-message-author-role="assistant" data-message-id="a1">
                    <div class="markdown">
                      <p>Here is a full answer.</p>
                      <pre><code>partial code</code><button id="code-copy" aria-label="Copy code">Copy</button></pre>
                      <p>More final response text after the code block.</p>
                    </div>
                    <button id="turn-copy" data-testid="copy-turn-action-button" aria-label="Copy response">Copy</button>
                  </article>
                </main>
                """
            )
            await page.evaluate(
                """
                () => {
                  window.clicked = "";
                  document.querySelector("#code-copy").addEventListener("click", () => window.clicked = "PARTIAL_CODE");
                  document.querySelector("#turn-copy").addEventListener("click", () => window.clicked = "FULL_RESPONSE");
                }
                """
            )

            result = await page.evaluate(_CLICK_LATEST_COPY_BUTTON_JS, None)
            clicked = await page.evaluate("window.clicked || ''")

            self.assertEqual(result.get("reason"), "ok")
            self.assertEqual(clicked, "FULL_RESPONSE")
        finally:
            await browser.close()
            await playwright_context.__aexit__(None, None, None)


if __name__ == "__main__":
    unittest.main()
