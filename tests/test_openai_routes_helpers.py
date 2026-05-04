from __future__ import annotations

import sys
import types
import unittest

from starlette.requests import Request
from fastapi import HTTPException

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
    _build_page_extraction_note,
    _build_page_extraction_response_format,
    _detect_user_prefix_contract,
    _display_app_name,
    _derive_app_key,
    _infer_expected_item_count,
    _looks_like_instruction_prefix,
    _merge_header_rows_in_array,
    _structured_cardinality_mismatch,
    _should_use_line_cardinality_fallback,
    _validate_chat_request,
)
from src.api.browser_gate import browser_access_lock
from src.api import routes as native_routes
from src.api import openai_routes as openai_routes_module
from src.api.attachment_expander import AttachmentPageDescriptor
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
    def test_route_families_share_browser_access_lock(self) -> None:
        self.assertIs(native_routes.browser_access_lock, browser_access_lock)
        self.assertIs(openai_routes_module.browser_access_lock, browser_access_lock)

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
        self.assertTrue(tail.endswith("URL: two\nTitle: beta article"))

    def test_detect_user_prefix_contract_rejects_short_or_non_instruction_prefix(self) -> None:
        prev_text = ("hello world\n" * 20) + "tail one"
        curr_text = ("hello world\n" * 20) + "tail two"
        self.assertIsNone(_detect_user_prefix_contract(prev_text, curr_text))

    def test_detect_user_prefix_contract_with_text_content_marker(self) -> None:
        fixed = (
            "[System instruction: You must respond with valid JSON only]\n"
            "You are an expert tagger.\n"
            "Rules apply.\n"
            "<TEXT_CONTENT>\n"
        )
        prev_text = fixed + ("A" * 1500)
        curr_text = fixed + ("B" * 1500)
        detected = _detect_user_prefix_contract(prev_text, curr_text)
        self.assertIsNotNone(detected)
        assert detected is not None
        _, tail = detected
        self.assertEqual(tail, "B" * 1500)

    def test_validate_chat_request_rejects_unsupported_model(self) -> None:
        req = ChatCompletionRequest(
            model="not-a-real-model",
            messages=[ChatMessage(role="user", content="hello")],
        )
        with self.assertRaises(HTTPException) as ctx:
            _validate_chat_request(req)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Unsupported model", ctx.exception.detail)

    def test_validate_chat_request_rejects_unknown_page_extraction_mode(self) -> None:
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="hello")],
            page_extraction={"mode": "table"},
        )
        with self.assertRaises(HTTPException) as ctx:
            _validate_chat_request(req)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("Unsupported page_extraction.mode", ctx.exception.detail)

    def test_validate_chat_request_rejects_page_extraction_with_response_format(self) -> None:
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="hello")],
            response_format="json_object",
            page_extraction={"mode": "structured"},
        )
        with self.assertRaises(HTTPException) as ctx:
            _validate_chat_request(req)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("manages response_format automatically", ctx.exception.detail)

    def test_build_page_extraction_note_lists_pages(self) -> None:
        note = _build_page_extraction_note(
            [
                AttachmentPageDescriptor(source_name="contract.pdf", page_number=1, page_index=1, source_kind="pdf"),
                AttachmentPageDescriptor(source_name="contract.pdf", page_number=2, page_index=2, source_kind="pdf"),
            ]
        )
        self.assertIn("[Per-page extraction]", note)
        self.assertIn("exactly 2 item(s)", note)
        self.assertIn("page_index=1", note)
        self.assertIn("page 2", note)

    def test_build_page_extraction_response_format_requires_pages_array(self) -> None:
        response_format = _build_page_extraction_response_format(
            [AttachmentPageDescriptor(source_name="doc.pdf", page_number=1, page_index=1, source_kind="pdf")]
        )
        self.assertEqual(response_format["type"], "json_schema")
        schema = response_format["json_schema"]["schema"]
        self.assertIn("pages", schema["properties"])
        self.assertEqual(schema["required"], ["pages"])

    def test_structured_cardinality_mismatch_uses_explicit_expected_count(self) -> None:
        messages = [ChatMessage(role="user", content="single page")]
        response_text = '{"pages":[{"page_index":1,"source_name":"a.pdf","page_number":1,"text":"a"}]}'
        self.assertIsNone(_structured_cardinality_mismatch(messages, response_text, expected_count=1))
        mismatch = _structured_cardinality_mismatch(messages, '{"pages":[]}', expected_count=1)
        self.assertEqual(mismatch, (1, 0))


if __name__ == "__main__":
    unittest.main()
