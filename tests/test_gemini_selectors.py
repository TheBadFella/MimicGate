from __future__ import annotations

import unittest

from src.gemini.selectors import GeminiSelectors


class GeminiSelectorsTests(unittest.TestCase):
    def test_selector_lists_non_empty(self) -> None:
        """Verify all critical selector lists are defined and non-empty."""
        self.assertTrue(len(GeminiSelectors.CHAT_INPUT) > 0)
        self.assertTrue(len(GeminiSelectors.SEND_BUTTON) > 0)
        self.assertTrue(len(GeminiSelectors.STOP_BUTTON) > 0)
        self.assertTrue(len(GeminiSelectors.MODEL_SWITCHER_BUTTON) > 0)
        self.assertTrue(len(GeminiSelectors.CURRENT_MODEL_LABEL) > 0)
        self.assertTrue(len(GeminiSelectors.ASSISTANT_MESSAGE) > 0)
        self.assertTrue(len(GeminiSelectors.ASSISTANT_MARKDOWN) > 0)
        self.assertTrue(len(GeminiSelectors.USER_MESSAGE) > 0)
        self.assertTrue(len(GeminiSelectors.COPY_BUTTON) > 0)
        self.assertTrue(len(GeminiSelectors.NEW_CHAT_BUTTON) > 0)
        self.assertTrue(len(GeminiSelectors.LOGIN_INDICATORS) > 0)
        self.assertTrue(len(GeminiSelectors.LOGGED_IN_INDICATORS) > 0)

    def test_chat_input_contains_quill_editor(self) -> None:
        """Ensure Quill editor and rich-textarea are present in input selectors."""
        joined = " ".join(GeminiSelectors.CHAT_INPUT)
        self.assertIn("ql-editor", joined)
        self.assertIn("rich-textarea", joined)

    def test_mode_switcher_targets_bard_mode_menu_button(self) -> None:
        """Verify model switcher targets the captured bard-mode-menu-button."""
        self.assertIn(
            "button[data-test-id='bard-mode-menu-button']",
            GeminiSelectors.MODEL_SWITCHER_BUTTON,
        )

    def test_send_button_excludes_stop_button(self) -> None:
        """Verify generic and container send button selectors exclude the stop button."""
        container_selector = "div[data-test-id='send-button-container'] button:not([aria-label*='Stop' i])"
        self.assertIn(container_selector, GeminiSelectors.SEND_BUTTON)
        for selector in GeminiSelectors.SEND_BUTTON:
            if "send-button-container" in selector or "send-button" in selector:
                if "aria-label*='Send" not in selector:
                    self.assertIn("not([aria-label*='Stop' i])", selector)


if __name__ == "__main__":
    unittest.main()
