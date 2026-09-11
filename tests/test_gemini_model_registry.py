from __future__ import annotations

import unittest

from src.gemini.model_registry import (
    PUBLIC_GEMINI_BROWSER_MODEL_ID,
    list_gemini_model_ids,
    normalize_token,
    resolve_gemini_model,
)


class GeminiModelRegistryTests(unittest.TestCase):
    def test_normalize_token(self) -> None:
        self.assertEqual(normalize_token("3.8 Flash"), "38flash")
        self.assertEqual(normalize_token("gemini-3.1-pro"), "gemini31pro")
        self.assertEqual(normalize_token("Extended thinking"), "extendedthinking")

    def test_list_gemini_model_ids(self) -> None:
        ids = list_gemini_model_ids()
        self.assertIn(PUBLIC_GEMINI_BROWSER_MODEL_ID, ids)
        self.assertIn("gemini-3.8-flash", ids)
        self.assertIn("gemini-3.6-flash", ids)
        self.assertIn("gemini-3.5-flash-lite", ids)
        self.assertIn("gemini-3.1-pro", ids)
        self.assertIn("gemini-extended-thinking", ids)

    def test_resolve_auto_model_ids_return_none(self) -> None:
        for model in ("", "auto", "default", "browser", PUBLIC_GEMINI_BROWSER_MODEL_ID):
            self.assertIsNone(resolve_gemini_model(model))

    def test_resolve_concrete_models(self) -> None:
        # Flash 3.8
        res_flash = resolve_gemini_model("gemini-3.8-flash")
        self.assertIsNotNone(res_flash)
        self.assertEqual(res_flash.ui_label, "3.8 Flash")

        # Flash 3.6
        res_flash36 = resolve_gemini_model("gemini-3.6-flash")
        self.assertIsNotNone(res_flash36)
        self.assertEqual(res_flash36.ui_label, "3.6 Flash")

        # Flash-Lite
        res_lite = resolve_gemini_model("gemini-3.5-flash-lite")
        self.assertIsNotNone(res_lite)
        self.assertEqual(res_lite.ui_label, "3.5 Flash-Lite")

        # Pro 3.1
        res_pro = resolve_gemini_model("gemini-3.1-pro")
        self.assertIsNotNone(res_pro)
        self.assertEqual(res_pro.ui_label, "3.1 Pro")

        # Extended thinking
        res_thinking = resolve_gemini_model("gemini-extended-thinking")
        self.assertIsNotNone(res_thinking)
        self.assertEqual(res_thinking.ui_label, "Extended thinking")

    def test_resolve_aliases(self) -> None:
        self.assertEqual(resolve_gemini_model("gemini-flash").ui_label, "Flash")
        self.assertEqual(resolve_gemini_model("gemini-pro").ui_label, "3.1 Pro")


if __name__ == "__main__":
    unittest.main()
