from __future__ import annotations

import unittest

from unittest.mock import AsyncMock, MagicMock

from src.gemini.detector import (
    _DOM_EXTRACT_JS,
    extract_latest_assistant_code_block_text,
    is_incomplete_response_text,
    normalize_assistant_text,
)


class GeminiDetectorTests(unittest.TestCase):
    def test_normalize_assistant_text(self) -> None:
        self.assertEqual(normalize_assistant_text("  Hello world!  "), "Hello world!")
        self.assertEqual(normalize_assistant_text(None), "")

    def test_is_incomplete_response_text(self) -> None:
        # Empty text is incomplete
        self.assertTrue(is_incomplete_response_text(""))
        self.assertTrue(is_incomplete_response_text(None))

        # Transient thinking states are incomplete
        self.assertTrue(is_incomplete_response_text("Thinking..."))
        self.assertTrue(is_incomplete_response_text("Working on your request, please wait."))

        # Substantial completed response is not incomplete
        self.assertFalse(
            is_incomplete_response_text(
                "Here is the answer to your question about quantum physics: "
                "Quantum mechanics is a fundamental theory in physics that describes the physical "
                "properties of nature at the scale of atoms and subatomic particles."
            )
        )

    def test_dom_fallback_keeps_code_blocks(self) -> None:
        self.assertNotIn("el.remove()", _DOM_EXTRACT_JS)


class GeminiDetectorAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_extract_latest_code_block_for_tool_payload(self) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock(return_value='{"tool_calls":[{"name":"lookup","arguments":{}}]}')
        text = await extract_latest_assistant_code_block_text(page)
        self.assertIn('"tool_calls"', text)


if __name__ == "__main__":
    unittest.main()
