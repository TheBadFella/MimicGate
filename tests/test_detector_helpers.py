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
    _conversation_snapshot,
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
    async def asyncSetUp(self) -> None:
        playwright_context = async_playwright()
        if playwright_context is None:
            self.skipTest("patchright is not installed")

        self.playwright_context = playwright_context
        self.playwright = await playwright_context.__aenter__()
        chrome_path = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        launch_options = {"headless": True}
        if chrome_path.exists():
            launch_options["executable_path"] = str(chrome_path)

        try:
            self.browser = await self.playwright.chromium.launch(**launch_options)
        except Exception as exc:
            await playwright_context.__aexit__(None, None, None)
            self.skipTest(f"browser runtime is not available: {exc}")

    async def asyncTearDown(self) -> None:
        await self.browser.close()
        await self.playwright_context.__aexit__(None, None, None)

    async def test_latest_turn_copy_ignores_code_block_copy_buttons(self) -> None:
        context = await self.browser.new_context()
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
        await context.close()

    async def test_latest_turn_copy_ignores_table_copy_button(self) -> None:
        context = await self.browser.new_context()
        page = await context.new_page()
        await page.set_content(
            """
            <!doctype html>
            <main>
              <article data-message-author-role="assistant" data-message-id="a1">
                <div class="markdown">
                  <p>Here is a full answer with a markdown table.</p>
                  <div class="_tableContainer">
                    <div tabindex="-1" class="group _tableWrapper flex flex-col-reverse w-fit">
                      <table data-start="1" data-end="42">
                        <thead><tr><th>Column1</th><th>Column2</th></tr></thead>
                        <tbody><tr><td>one</td><td>two</td></tr></tbody>
                      </table>
                      <div class="relative h-0 self-end select-none">
                        <div class="absolute end-0 flex items-end">
                          <span data-state="closed">
                            <button id="table-copy" aria-label="Copy Table">Copy Table</button>
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                  <p>More final response text after the table.</p>
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
              document.querySelector("#table-copy").addEventListener("click", () => window.clicked = "TABLE_ONLY");
              document.querySelector("#turn-copy").addEventListener("click", () => window.clicked = "FULL_RESPONSE");
            }
            """
        )

        result = await page.evaluate(_CLICK_LATEST_COPY_BUTTON_JS, None)
        clicked = await page.evaluate("window.clicked || ''")

        self.assertEqual(result.get("reason"), "ok")
        self.assertEqual(clicked, "FULL_RESPONSE")
        await context.close()

    async def test_table_copy_button_does_not_signal_response_complete(self) -> None:
        context = await self.browser.new_context()
        page = await context.new_page()
        await page.set_content(
            """
            <!doctype html>
            <main>
              <article data-message-author-role="assistant" data-message-id="a1">
                <div class="markdown">
                  <p>Streaming response with a table.</p>
                  <div class="_tableContainer">
                    <div class="_tableWrapper">
                      <table><tbody><tr><td>partial</td></tr></tbody></table>
                      <div><button id="table-copy" aria-label="Copy Table">Copy Table</button></div>
                    </div>
                  </div>
                </div>
              </article>
            </main>
            """
        )

        snapshot = await _conversation_snapshot(page)

        self.assertEqual(snapshot.get("copyButtonCount"), 0)
        self.assertFalse(snapshot["latestAssistant"]["hasCopyButton"])
        await context.close()


if __name__ == "__main__":
    unittest.main()
