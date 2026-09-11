from __future__ import annotations

import unittest

from src.gemini.detector import is_incomplete_response_text, normalize_assistant_text


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


if __name__ == "__main__":
    unittest.main()
