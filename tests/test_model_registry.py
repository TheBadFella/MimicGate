from __future__ import annotations

import unittest
from unittest.mock import patch

from src.chatgpt import model_registry


class ModelRegistryTests(unittest.TestCase):
    def test_public_models_include_browser_alias_and_configured_models(self) -> None:
        with patch.object(model_registry.Config, "CHATGPT_MODEL_ALIASES", "gpt-5.3=GPT-5.3,o3=o3"):
            self.assertEqual(
                model_registry.list_public_chat_models(),
                ["catgpt-browser", "gpt-5.3", "o3"],
            )

    def test_default_models_do_not_include_unavailable_future_aliases(self) -> None:
        self.assertNotIn("gpt-5.5", model_registry.list_public_chat_models())
        self.assertFalse(model_registry.is_supported_chat_model("gpt-5.5"))

    def test_supported_model_accepts_public_id_and_ui_label(self) -> None:
        with patch.object(model_registry.Config, "CHATGPT_MODEL_ALIASES", "gpt-4.1-mini=GPT-4.1 mini"):
            self.assertTrue(model_registry.is_supported_chat_model("gpt-4.1-mini"))
            self.assertTrue(model_registry.is_supported_chat_model("GPT-4.1 mini"))

    def test_resolve_requested_model_uses_default_for_browser_alias(self) -> None:
        with patch.object(model_registry.Config, "CHATGPT_MODEL_ALIASES", "gpt-5.3=GPT-5.3,o3=o3"), patch.object(
            model_registry.Config,
            "CHATGPT_DEFAULT_MODEL",
            "o3",
        ):
            resolved = model_registry.resolve_requested_model("catgpt-browser")
            self.assertIsNotNone(resolved)
            assert resolved is not None
            self.assertEqual(resolved.public_id, "o3")
            self.assertEqual(resolved.ui_label, "o3")

    def test_resolve_requested_model_returns_none_for_browser_alias_without_default(self) -> None:
        with patch.object(model_registry.Config, "CHATGPT_MODEL_ALIASES", "gpt-5.3=GPT-5.3"), patch.object(
            model_registry.Config,
            "CHATGPT_DEFAULT_MODEL",
            "",
        ):
            self.assertIsNone(model_registry.resolve_requested_model("catgpt-browser"))


if __name__ == "__main__":
    unittest.main()
