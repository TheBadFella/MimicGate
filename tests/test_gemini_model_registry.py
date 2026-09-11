from __future__ import annotations

import unittest

from src.gemini.model_registry import (
    PUBLIC_GEMINI_BROWSER_MODEL_ID,
    canonical_reasoning_effort,
    is_auto_model,
    list_gemini_model_ids,
    normalize_token,
    register_discovered_gemini_models,
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
        for model in ("", "auto", "default", "browser", PUBLIC_GEMINI_BROWSER_MODEL_ID, "catgpt-browser", "claude-browser", "gpt-4o", "gpt-4", "gpt-3.5-turbo"):
            self.assertIsNone(resolve_gemini_model(model))
            self.assertTrue(is_auto_model(model))


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

    def test_canonical_reasoning_effort(self) -> None:
        self.assertEqual(canonical_reasoning_effort("high"), "high")
        self.assertEqual(canonical_reasoning_effort("extended"), "extended")
        self.assertEqual(canonical_reasoning_effort("max"), "max")
        self.assertEqual(canonical_reasoning_effort("deep"), "extended")
        self.assertEqual(canonical_reasoning_effort("thinking"), "extended")
        self.assertEqual(canonical_reasoning_effort("complex"), "extended")
        self.assertEqual(canonical_reasoning_effort("low"), "low")
        self.assertEqual(canonical_reasoning_effort("none"), "none")
        self.assertEqual(canonical_reasoning_effort("disabled"), "none")
        self.assertEqual(canonical_reasoning_effort("medium"), "medium")
        self.assertEqual(canonical_reasoning_effort("standard"), "medium")
        self.assertIsNone(canonical_reasoning_effort("unknown-effort"))
        self.assertIsNone(canonical_reasoning_effort(None))

    def test_resolve_with_reasoning_effort(self) -> None:
        # High reasoning routes to Extended thinking
        res_high = resolve_gemini_model("gemini-browser", reasoning_effort="high")
        self.assertIsNotNone(res_high)
        self.assertEqual(res_high.ui_label, "Extended thinking")

        res_extended = resolve_gemini_model("gemini-3.8-flash", reasoning_effort="extended")
        self.assertIsNotNone(res_extended)
        self.assertEqual(res_extended.ui_label, "Extended thinking")

        # Low reasoning with auto model routes to 3.8 Flash
        res_low_auto = resolve_gemini_model("auto", reasoning_effort="low")
        self.assertIsNotNone(res_low_auto)
        self.assertEqual(res_low_auto.ui_label, "3.8 Flash")

        # Low reasoning with pro model routes to 3.1 Pro
        res_low_pro = resolve_gemini_model("gemini-pro", reasoning_effort="low")
        self.assertIsNotNone(res_low_pro)
        self.assertEqual(res_low_pro.ui_label, "3.1 Pro")

        # Low reasoning with thinking model routes to non-thinking (Flash)
        res_low_thinking = resolve_gemini_model("gemini-extended-thinking", reasoning_effort="low")
        self.assertIsNotNone(res_low_thinking)
        self.assertEqual(res_low_thinking.ui_label, "3.8 Flash")

    def test_register_discovered_models(self) -> None:
        discovered = register_discovered_gemini_models(["Custom Gemini Model\nCustom Subtitle"])
        self.assertIn("gemini-custom-gemini-model", discovered)
        self.assertIn("gemini-custom-gemini-model", list_gemini_model_ids())

        resolved = resolve_gemini_model("gemini-custom-gemini-model")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.ui_label, "Custom Gemini Model")


if __name__ == "__main__":
    unittest.main()
