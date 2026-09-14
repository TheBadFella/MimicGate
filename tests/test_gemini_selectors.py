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

    def test_sidebar_and_deletion_selectors_defined(self) -> None:
        """Verify sidebar toggle, items, menu, and deletion selectors are defined."""
        self.assertTrue(len(GeminiSelectors.SIDEBAR_TOGGLE_BUTTON) > 0)
        self.assertTrue(len(GeminiSelectors.SIDEBAR_THREAD_ITEM) > 0)
        self.assertTrue(len(GeminiSelectors.SIDEBAR_THREAD_MENU_BUTTON) > 0)
        self.assertTrue(len(GeminiSelectors.THREAD_DELETE_OPTION) > 0)
        self.assertTrue(len(GeminiSelectors.THREAD_CONFIRM_DELETE_BUTTON) > 0)
        self.assertTrue(len(GeminiSelectors.CONVERSATION_TITLE_ELEMENTS) > 0)
        self.assertIn("button[aria-label*='Main menu' i]", GeminiSelectors.SIDEBAR_TOGGLE_BUTTON)
        self.assertIn("conversation-action-menu button", GeminiSelectors.SIDEBAR_THREAD_MENU_BUTTON)
        self.assertIn("[role='menuitem']:has-text('Delete')", GeminiSelectors.THREAD_DELETE_OPTION)

    def test_tts_and_media_selectors_defined(self) -> None:
        """Verify TTS listen button, generated images, and error indicators are defined."""
        self.assertTrue(len(GeminiSelectors.TTS_BUTTON) > 0)
        self.assertTrue(len(GeminiSelectors.GENERATED_IMAGE) > 0)
        self.assertTrue(len(GeminiSelectors.IMAGE_DOWNLOAD_BUTTON) > 0)
        self.assertTrue(len(GeminiSelectors.ERROR_INDICATORS) > 0)
        self.assertIn("button.tts-button", GeminiSelectors.TTS_BUTTON)
        self.assertIn("button[aria-label='Listen' i]", GeminiSelectors.TTS_BUTTON)
        self.assertIn("img[src*='googleusercontent.com/chat_attachment']", GeminiSelectors.GENERATED_IMAGE)
        self.assertIn("div:has-text('reached your limit')", GeminiSelectors.ERROR_INDICATORS)


if __name__ == "__main__":
    unittest.main()
