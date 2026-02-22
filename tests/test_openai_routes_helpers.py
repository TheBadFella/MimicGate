from __future__ import annotations

import sys
import types
import unittest

from starlette.requests import Request

# Provide a minimal patchright stub so helper tests can import API modules
# without requiring browser automation dependencies.
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

from src.api.openai_routes import (
    _detect_user_prefix_contract,
    _display_app_name,
    _derive_app_key,
    _infer_expected_item_count,
    _looks_like_instruction_prefix,
    _merge_header_rows_in_array,
    _should_use_line_cardinality_fallback,
)
from src.api.openai_schemas import ChatCompletionRequest, ChatMessage


def _make_request(headers: dict[str, str] | None = None, client_host: str = "127.0.0.1") -> Request:
    hdrs = []
    for key, value in (headers or {}).items():
        hdrs.append((key.lower().encode("latin-1"), value.encode("latin-1")))

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/chat/completions",
        "headers": hdrs,
        "client": (client_host, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
    }
    return Request(scope)


class OpenAIRoutesHelpersTests(unittest.TestCase):
    def test_derive_app_key_prefers_user(self) -> None:
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="hello")],
            user="KaraKeep",
        )
        http_req = _make_request({"x-app-name": "mealie"})
        app_key = _derive_app_key(req, http_req)
        self.assertEqual(app_key, "user:karakeep")

    def test_derive_app_key_uses_app_header(self) -> None:
        req = ChatCompletionRequest(messages=[ChatMessage(role="user", content="hello")])
        http_req = _make_request({"x-app-name": "KaraKeep"})
        app_key = _derive_app_key(req, http_req)
        self.assertEqual(app_key, "hdr:x-app-name:karakeep")

    def test_derive_app_key_falls_back_to_origin(self) -> None:
        req = ChatCompletionRequest(messages=[ChatMessage(role="user", content="hello")])
        http_req = _make_request({"origin": "https://app.example.com/path"})
        app_key = _derive_app_key(req, http_req)
        self.assertEqual(app_key, "origin:app.example.com")

    def test_derive_app_key_prefers_endpoint_name(self) -> None:
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="hello")],
            user="karakeep",
        )
        http_req = _make_request({"x-app-name": "mealie"})
        app_key = _derive_app_key(req, http_req, endpoint_app_name="linkwarden")
        self.assertEqual(app_key, "endpoint:linkwarden")

    def test_display_app_name_from_user_key(self) -> None:
        self.assertEqual(_display_app_name("user:karakeep"), "karakeep")

    def test_display_app_name_from_header_key(self) -> None:
        self.assertEqual(_display_app_name("hdr:x-app-name:mealie"), "mealie")

    def test_line_fallback_rejects_instruction_heavy_prompt(self) -> None:
        text = (
            "[System instructions]\n"
            "You must respond with valid JSON only.\n"
            "$schema: http://json-schema.org/draft-07/schema#\n"
            "<TEXT_CONTENT>\n"
            "TABLE OF CONTENTS\n"
        )
        self.assertFalse(_should_use_line_cardinality_fallback(text))

    def test_line_fallback_accepts_compact_item_list(self) -> None:
        text = "one line\nsecond line\nthird line"
        self.assertTrue(_should_use_line_cardinality_fallback(text))

    def test_infer_expected_item_count_from_json_array(self) -> None:
        messages = [
            ChatMessage(
                role="user",
                content='{"ingredients":[{"food":"salt"},{"food":"pepper"},{"food":"oil"}]}',
            )
        ]
        self.assertEqual(_infer_expected_item_count(messages), 3)

    def test_infer_expected_item_count_skips_instruction_prompt(self) -> None:
        prompt = (
            "[System instructions]\n"
            "You must respond with valid JSON only.\n"
            "$schema\n"
            "<TEXT_CONTENT>\n"
            "line A\nline B\nline C\n"
        )
        messages = [ChatMessage(role="user", content=prompt)]
        self.assertIsNone(_infer_expected_item_count(messages))

    def test_merge_header_rows_moves_header_into_next_note(self) -> None:
        items = [
            {"quantity": None, "unit": None, "food": None, "note": "TO SERVE"},
            {"quantity": 8, "unit": None, "food": "chapattis", "note": None},
        ]
        merged = _merge_header_rows_in_array(items)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["food"], "chapattis")
        self.assertEqual(merged[0]["note"], "TO SERVE")

    def test_instruction_prefix_heuristic_detects_prompt_markers(self) -> None:
        text = (
            "[System instruction: You must respond with valid JSON only]\n"
            "Follow it strictly.\n"
            "<TEXT_CONTENT>\n"
        )
        self.assertTrue(_looks_like_instruction_prefix(text))

    def test_detect_user_prefix_contract_finds_large_shared_prefix(self) -> None:
        prefix = (
            "[System instruction: You must respond with valid JSON only]\n"
            "You are an expert tagger.\n"
            "Follow it strictly.\n"
            "<TEXT_CONTENT>\n"
            + ("A" * 500)
            + "\n"
        )
        prev_text = prefix + "URL: one\nTitle: alpha article"
        curr_text = prefix + "URL: two\nTitle: beta article"
        detected = _detect_user_prefix_contract(prev_text, curr_text)
        self.assertIsNotNone(detected)
        assert detected is not None
        found_prefix, tail = detected
        self.assertTrue(found_prefix.startswith("[System instruction"))
        self.assertEqual(tail, "URL: two\nTitle: beta article")

    def test_detect_user_prefix_contract_rejects_short_or_non_instruction_prefix(self) -> None:
        prev_text = ("hello world\n" * 20) + "tail one"
        curr_text = ("hello world\n" * 20) + "tail two"
        self.assertIsNone(_detect_user_prefix_contract(prev_text, curr_text))


if __name__ == "__main__":
    unittest.main()
