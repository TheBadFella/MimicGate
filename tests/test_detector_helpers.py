from __future__ import annotations

import sys
import types
import unittest


if "patchright" not in sys.modules:
    patchright_mod = types.ModuleType("patchright")
    async_api_mod = types.ModuleType("patchright.async_api")
    async_api_mod.Page = object
    async_api_mod.BrowserContext = object
    async_api_mod.Playwright = object
    async_api_mod.Frame = object
    async_api_mod.Request = object
    async_api_mod.Response = object

    async def _fake_async_playwright():
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


from src.chatgpt.detector import is_incomplete_response_text, normalize_assistant_text


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


if __name__ == "__main__":
    unittest.main()
