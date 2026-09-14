from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from src.api import openai_routes
from src.chatgpt.errors import PromptAttachmentFallbackError, PromptTooLongError
from src.chatgpt.models import ChatResponse, ImageInfo
from src.config import Config
from src.gemini.client import GeminiClient
from src.gemini.model_registry import PUBLIC_GEMINI_BROWSER_MODEL_ID
from src.gemini.selectors import GeminiSelectors


class GeminiProviderTests(unittest.IsolatedAsyncioTestCase):
    def test_config_methods_when_provider_is_gemini(self) -> None:
        with patch.object(Config, "PROVIDER", "gemini"):
            self.assertEqual(Config.provider_url(), f"{Config.GEMINI_URL}/app")
            self.assertEqual(Config.provider_name(), "Gemini")
            self.assertEqual(Config.provider_owner(), "google")
            self.assertTrue(Config.uses_browser())
            model_ids = Config.provider_model_ids()
            self.assertIn(PUBLIC_GEMINI_BROWSER_MODEL_ID, model_ids)
            self.assertIn("gemini-3.8-flash", model_ids)
            self.assertIn("gemini-3.1-pro", model_ids)
            self.assertEqual(Config.default_model_id(), Config.GEMINI_DEFAULT_MODEL)
            self.assertTrue(Config.supports_image_generation())

    def test_resolve_model_id_for_gemini(self) -> None:
        with patch.object(Config, "PROVIDER", "gemini"), \
             patch.object(openai_routes.Config, "PROVIDER", "gemini"), \
             patch.object(Config, "GEMINI_DEFAULT_MODEL", "gemini-browser"), \
             patch.object(openai_routes.Config, "GEMINI_DEFAULT_MODEL", "gemini-browser"):
            # Default / auto fallback preserves browser model
            self.assertEqual(
                openai_routes._resolve_model_id(None),
                "gemini-browser",
            )
            self.assertEqual(
                openai_routes._resolve_model_id("gemini-browser"),
                "gemini-browser",
            )
            self.assertEqual(
                openai_routes._resolve_model_id("catgpt-browser"),
                "gemini-browser",
            )
            self.assertEqual(
                openai_routes._resolve_model_id("gpt-4o"),
                "gemini-browser",
            )
            # Concrete models
            self.assertEqual(
                openai_routes._resolve_model_id("gemini-3.8-flash"),
                "gemini-3.8-flash",
            )
            self.assertEqual(
                openai_routes._resolve_model_id("gemini-3.1-pro"),
                "gemini-3.1-pro",
            )
            self.assertEqual(
                openai_routes._resolve_model_id("gemini-1.5-flash"),
                "gemini-1.5-flash",
            )
            # When GEMINI_MODEL_FALLBACK=True, unknown model falls back to default model gracefully
            with patch.object(Config, "GEMINI_MODEL_FALLBACK", True), patch.object(openai_routes.Config, "GEMINI_MODEL_FALLBACK", True):
                self.assertEqual(
                    openai_routes._resolve_model_id("unknown-nonexistent-model"),
                    "gemini-browser",
                )
                self.assertEqual(
                    openai_routes._resolve_model_id("gpt-5.6-sol"),
                    "gemini-browser",
                )
            # When GEMINI_MODEL_FALLBACK=False, unknown model raises HTTP 400 with helpful documentation link
            with patch.object(Config, "GEMINI_MODEL_FALLBACK", False), patch.object(openai_routes.Config, "GEMINI_MODEL_FALLBACK", False):
                with self.assertRaises(HTTPException) as cm:
                    openai_routes._resolve_model_id("unknown-nonexistent-model")
                self.assertEqual(cm.exception.status_code, 400)
                self.assertIn("not supported by provider Gemini", cm.exception.detail)
                self.assertIn("MODEL_SWITCHING.md", cm.exception.detail)
                # Auto and valid models should still succeed even with fallback disabled
                self.assertEqual(openai_routes._resolve_model_id("gemini-3.8-flash"), "gemini-3.8-flash")
                self.assertEqual(openai_routes._resolve_model_id("gemini-browser"), "gemini-browser")

    async def test_list_models_for_gemini(self) -> None:
        with patch.object(Config, "PROVIDER", "gemini"), patch.object(openai_routes.Config, "PROVIDER", "gemini"):
            response = await openai_routes.list_models()
            model_ids = [m.id for m in response.data]
            self.assertIn(PUBLIC_GEMINI_BROWSER_MODEL_ID, model_ids)
            self.assertIn("gemini-3.8-flash", model_ids)
            self.assertIn("gemini-3.1-pro", model_ids)
            for m in response.data:
                self.assertEqual(m.owned_by, "google")

    async def test_gemini_client_bind_page(self) -> None:
        mock_page1 = MagicMock()
        mock_page2 = MagicMock()
        client = GeminiClient(mock_page1)
        self.assertIs(client.page, mock_page1)

        bound = client.bind_page(mock_page2)
        self.assertIsNot(bound, client)
        self.assertIs(bound.page, mock_page2)
        self.assertIs(client.page, mock_page1)

    async def test_gemini_client_get_current_model(self) -> None:
        mock_page = MagicMock()
        mock_el = AsyncMock()
        mock_el.inner_text = AsyncMock(return_value="3.8 Flash\n")
        mock_page.query_selector = AsyncMock(return_value=mock_el)

        client = GeminiClient(mock_page)
        model = await client.get_current_model()
        self.assertEqual(model, "3.8 Flash")

    async def test_gemini_client_new_chat_from_existing_thread(self) -> None:
        mock_page = MagicMock()
        mock_page.url = "https://gemini.google.com/app/1a2b3c4d5e"
        mock_page.goto = AsyncMock()
        mock_page.click = AsyncMock()
        mock_el = MagicMock()
        mock_page.wait_for_selector = AsyncMock(return_value=mock_el)
        mock_page.query_selector = AsyncMock(return_value=None)

        client = GeminiClient(mock_page)
        # Must succeed and not raise RuntimeError
        await client.new_chat()
        mock_page.wait_for_selector.assert_awaited()

    async def test_gemini_client_new_chat_already_clean(self) -> None:
        mock_page = MagicMock()
        mock_page.url = "https://gemini.google.com/app"
        mock_page.query_selector_all = AsyncMock(return_value=[])
        mock_page.query_selector = AsyncMock(return_value=MagicMock())
        mock_page.wait_for_selector = AsyncMock(return_value=MagicMock())
        mock_page.evaluate = AsyncMock(return_value=0)
        mock_page.goto = AsyncMock()

        client = GeminiClient(mock_page)
        await client.new_chat()
        # Should not need full goto because already on clean new chat
        mock_page.goto.assert_not_awaited()

    async def test_click_send_skips_stop_button(self) -> None:
        mock_page = MagicMock()
        stop_el = AsyncMock()
        stop_el.is_visible = AsyncMock(return_value=True)
        stop_el.get_attribute = AsyncMock(side_effect=lambda attr: "Stop response" if attr == "aria-label" else None)
        mock_page.query_selector = AsyncMock(return_value=stop_el)

        client = GeminiClient(mock_page)
        with patch("src.gemini.client.human_click", new_callable=AsyncMock) as mock_click:
            result = await client._click_send(timeout_s=0.1)
            self.assertFalse(result)
            mock_click.assert_not_awaited()

    async def test_click_send_clicks_valid_send_button(self) -> None:
        mock_page = MagicMock()
        send_el = AsyncMock()
        send_el.is_visible = AsyncMock(return_value=True)
        send_el.get_attribute = AsyncMock(side_effect=lambda attr: "Send message" if attr == "aria-label" else None)
        send_el.query_selector = AsyncMock(return_value=None)
        mock_page.query_selector = AsyncMock(return_value=send_el)

        client = GeminiClient(mock_page)
        with patch("src.gemini.client.human_click", new_callable=AsyncMock) as mock_click:
            result = await client._click_send(timeout_s=0.5)
            self.assertTrue(result)
            mock_click.assert_awaited_once()

    async def test_send_message_calls_send_once(self) -> None:
        mock_page = MagicMock()
        mock_page.url = "https://gemini.google.com/app/test12345"
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.click = AsyncMock()
        mock_page.keyboard = MagicMock()
        mock_page.keyboard.press = AsyncMock()

        client = GeminiClient(mock_page)
        client._find_selector = AsyncMock(return_value="div.ql-editor")
        client._click_send = AsyncMock(return_value=True)

        with patch("src.gemini.client.human_type", new_callable=AsyncMock), \
             patch("src.gemini.client.count_assistant_messages", new_callable=AsyncMock, return_value=0), \
             patch("src.gemini.client.get_latest_assistant_turn_signature", new_callable=AsyncMock, return_value=None), \
             patch("src.gemini.client.wait_for_response_complete", new_callable=AsyncMock, return_value=True), \
             patch("src.gemini.client.extract_last_response_via_copy", new_callable=AsyncMock, return_value="Test response"):
            resp = await client.send_message("Hello Gemini")
            self.assertEqual(resp.message, "Test response")
            # Crucial check: _click_send is called exactly once, preventing double send / stop click
            self.assertEqual(client._click_send.await_count, 1)

    async def test_gemini_client_get_thread_title_from_page_title(self) -> None:
        mock_page = MagicMock()
        mock_page.url = "https://gemini.google.com/app/thread123"
        mock_page.title = AsyncMock(return_value="Python Performance Guide - Gemini")
        client = GeminiClient(mock_page)
        title = await client.get_thread_title("thread123")
        self.assertEqual(title, "Python Performance Guide")

    async def test_gemini_client_get_thread_title_from_list_threads(self) -> None:
        mock_page = MagicMock()
        mock_page.url = "https://gemini.google.com/app/different_thread"
        mock_page.title = AsyncMock(return_value="Gemini")
        client = GeminiClient(mock_page)
        client.list_threads = AsyncMock(return_value=[
            {"id": "target_id", "title": "Data Engineering Discussion", "url": "/app/target_id"}
        ])
        title = await client.get_thread_title("target_id")
        self.assertEqual(title, "Data Engineering Discussion")

    async def test_gemini_client_list_threads_does_not_duplicate_entries(self) -> None:
        mock_page = MagicMock()
        thread_link = AsyncMock()
        thread_link.is_visible = AsyncMock(return_value=True)
        thread_link.get_attribute = AsyncMock(
            side_effect=lambda attr: "/app/thread123" if attr == "href" else "A useful chat\nMore details"
        )
        thread_link.inner_text = AsyncMock(return_value="Fallback title")
        mock_page.query_selector = AsyncMock(return_value=thread_link)
        mock_page.query_selector_all = AsyncMock(return_value=[thread_link])

        threads = await GeminiClient(mock_page).list_threads()

        self.assertEqual(threads, [{"id": "thread123", "title": "A useful chat", "url": "/app/thread123"}])

    async def test_gemini_client_delete_thread_success(self) -> None:
        mock_page = MagicMock()
        mock_page.url = "https://gemini.google.com/app/to_delete"
        mock_page.goto = AsyncMock()

        thread_item = AsyncMock()
        thread_item.get_attribute = AsyncMock(return_value="/app/to_delete")
        thread_item.hover = AsyncMock()

        menu_btn = AsyncMock()
        menu_btn.click = AsyncMock()

        parent_handle = AsyncMock()
        parent_handle.query_selector = AsyncMock(return_value=menu_btn)
        thread_item.evaluate_handle = AsyncMock(return_value=parent_handle)

        delete_opt = AsyncMock()
        delete_opt.click = AsyncMock()

        confirm_btn = AsyncMock()
        confirm_btn.click = AsyncMock()

        mock_page.query_selector_all = AsyncMock(return_value=[thread_item])
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_page.wait_for_selector = AsyncMock(side_effect=[delete_opt, confirm_btn])

        client = GeminiClient(mock_page)
        client.navigate_to_thread = AsyncMock()

        ok = await client.delete_thread("to_delete")
        self.assertTrue(ok)
        client.navigate_to_thread.assert_awaited_once_with("to_delete")
        thread_item.hover.assert_awaited_once()
        menu_btn.click.assert_awaited_once()
        delete_opt.click.assert_awaited_once()
        confirm_btn.click.assert_awaited_once()

    async def test_gemini_client_delete_thread_not_found(self) -> None:
        mock_page = MagicMock()
        mock_page.query_selector_all = AsyncMock(return_value=[])
        mock_page.query_selector = AsyncMock(return_value=None)

        client = GeminiClient(mock_page)
        client.navigate_to_thread = AsyncMock()

        ok = await client.delete_thread("missing_thread")
        self.assertFalse(ok)

    async def test_maybe_delete_expired_app_threads_calls_gemini_delete(self) -> None:
        mock_client = MagicMock(spec=GeminiClient)
        mock_client.delete_thread = AsyncMock(return_value=True)

        mock_page = MagicMock()
        mock_lease = MagicMock()
        mock_lease.page = mock_page

        with patch.object(openai_routes.Config, "API_APP_THREAD_DELETE_EXPIRED", True), \
             patch.object(openai_routes, "_get_client", return_value=mock_client), \
             patch.object(openai_routes, "_bind_client", return_value=mock_client), \
             patch("src.api.openai_routes.acquire_browser_page") as mock_acquire:
            mock_acquire.return_value.__aenter__.return_value = mock_lease
            mock_acquire.return_value.__aexit__.return_value = None

            await openai_routes._maybe_delete_expired_app_threads(["gem-thread-1", "gem-thread-2"])
            self.assertEqual(mock_client.delete_thread.await_count, 2)
            mock_client.delete_thread.assert_any_await("gem-thread-1")
            mock_client.delete_thread.assert_any_await("gem-thread-2")

    async def test_gemini_client_switch_model_with_reasoning_effort(self) -> None:
        mock_page = MagicMock()
        mock_page.click = AsyncMock()
        mock_page.wait_for_selector = AsyncMock()
        mock_page.keyboard = MagicMock()
        mock_page.keyboard.press = AsyncMock()

        item_el = AsyncMock()
        item_el.inner_text = AsyncMock(return_value="Extended thinking\nComplex problem solving")
        item_el.click = AsyncMock()

        mock_page.query_selector_all = AsyncMock(return_value=[item_el])

        client = GeminiClient(mock_page)
        client.get_current_model = AsyncMock(side_effect=["3.8 Flash", "Extended thinking"])
        client._find_selector = AsyncMock(return_value="button[data-test-id='bard-mode-menu-button']")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            switched = await client.switch_model("gemini-browser", reasoning_effort="high")
            self.assertTrue(switched)
            item_el.click.assert_awaited_once()

    async def test_gemini_client_switch_model_does_not_cross_match_versions(self) -> None:
        mock_page = MagicMock()
        mock_page.click = AsyncMock()
        mock_page.wait_for_selector = AsyncMock()
        older = AsyncMock()
        older.inner_text = AsyncMock(return_value="3.6 Flash\nAll-around help")
        newer = AsyncMock()
        newer.inner_text = AsyncMock(return_value="3.8 Flash\nFast responses")
        mock_page.query_selector_all = AsyncMock(return_value=[older, newer])

        client = GeminiClient(mock_page)
        client.get_current_model = AsyncMock(side_effect=["3.6 Flash", "3.8 Flash"])
        client._find_selector = AsyncMock(return_value="button[data-test-id='bard-mode-menu-button']")
        with patch("asyncio.sleep", new_callable=AsyncMock):
            self.assertTrue(await client.switch_model("gemini-3.8-flash"))

        older.click.assert_not_awaited()
        newer.click.assert_awaited_once()

    async def test_gemini_client_switch_model_reports_selection_that_did_not_stick(self) -> None:
        mock_page = MagicMock()
        mock_page.click = AsyncMock()
        mock_page.wait_for_selector = AsyncMock()
        item = AsyncMock()
        item.inner_text = AsyncMock(return_value="3.8 Flash")
        mock_page.query_selector_all = AsyncMock(return_value=[item])
        client = GeminiClient(mock_page)
        client.get_current_model = AsyncMock(side_effect=["3.6 Flash", "3.6 Flash"])
        client._find_selector = AsyncMock(return_value="model-switcher")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            self.assertFalse(await client.switch_model("gemini-3.8-flash"))

    async def test_openai_tool_payload_uses_gemini_detector(self) -> None:
        mock_page = MagicMock()
        payload = '{"tool_calls":[{"name":"lookup","arguments":{"line":"a\\nb"}}]}'
        mock_page.evaluate = AsyncMock(return_value=payload)
        client = GeminiClient(mock_page)

        self.assertEqual(await openai_routes._latest_lossless_tool_payload(client), payload)

    async def test_gemini_client_discover_available_models(self) -> None:
        mock_page = MagicMock()
        mock_page.click = AsyncMock()
        mock_page.wait_for_selector = AsyncMock()
        mock_page.keyboard = MagicMock()
        mock_page.keyboard.press = AsyncMock()

        item1 = AsyncMock()
        item1.inner_text = AsyncMock(return_value="3.5 Flash-Lite\nFastest answers")
        item1.get_attribute = AsyncMock(return_value="true")
        item1.click = AsyncMock()

        item2 = AsyncMock()
        item2.inner_text = AsyncMock(return_value="3.6 Flash\nAll-around help")
        item2.get_attribute = AsyncMock(return_value=None)

        mock_page.query_selector_all = AsyncMock(return_value=[item1, item2])

        client = GeminiClient(mock_page)
        client._find_selector = AsyncMock(return_value="button[data-test-id='bard-mode-menu-button']")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            models = await client.discover_available_models(force=True)
            self.assertIn("gemini-3.5-flash-lite", models)
            self.assertIn("gemini-3.6-flash", models)

    async def test_gemini_client_trigger_tts(self) -> None:
        mock_page = MagicMock()
        response_root = AsyncMock()
        btn = AsyncMock()
        btn.is_visible = AsyncMock(return_value=True)
        btn.click = AsyncMock()
        response_root.query_selector = AsyncMock(return_value=btn)
        mock_page.query_selector_all = AsyncMock(return_value=[response_root])

        client = GeminiClient(mock_page)
        result = await client._trigger_tts()
        self.assertTrue(result)
        btn.click.assert_awaited_once()

    async def test_gemini_client_trigger_tts_from_response_menu(self) -> None:
        mock_page = MagicMock()
        mock_page.keyboard = MagicMock()
        mock_page.keyboard.press = AsyncMock()
        response_root = AsyncMock()
        more_btn = AsyncMock()
        more_btn.is_visible = AsyncMock(return_value=True)
        more_btn.click = AsyncMock()
        menu_item = AsyncMock()
        menu_item.is_visible = AsyncMock(return_value=True)
        menu_item.click = AsyncMock()

        async def root_query(selector: str):
            if selector == GeminiSelectors.RESPONSE_MORE_BUTTON[0]:
                return more_btn
            return None

        response_root.query_selector = AsyncMock(side_effect=root_query)
        mock_page.query_selector_all = AsyncMock(return_value=[response_root])
        mock_page.query_selector = AsyncMock(return_value=menu_item)

        client = GeminiClient(mock_page)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._trigger_tts()

        self.assertTrue(result)
        more_btn.click.assert_awaited_once()
        menu_item.click.assert_awaited_once()

    async def test_gemini_client_trigger_tts_closes_empty_response_menu(self) -> None:
        mock_page = MagicMock()
        mock_page.keyboard = MagicMock()
        mock_page.keyboard.press = AsyncMock()
        response_root = AsyncMock()
        more_btn = AsyncMock()
        more_btn.is_visible = AsyncMock(return_value=True)
        more_btn.click = AsyncMock()

        async def root_query(selector: str):
            if selector == GeminiSelectors.RESPONSE_MORE_BUTTON[0]:
                return more_btn
            return None

        response_root.query_selector = AsyncMock(side_effect=root_query)
        mock_page.query_selector_all = AsyncMock(return_value=[response_root])
        mock_page.query_selector = AsyncMock(return_value=None)

        client = GeminiClient(mock_page)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._trigger_tts()

        self.assertFalse(result)
        mock_page.keyboard.press.assert_awaited_once_with("Escape")

    async def test_gemini_client_detect_page_error(self) -> None:
        mock_page = MagicMock()
        err_banner = AsyncMock()
        err_banner.is_visible = AsyncMock(return_value=True)
        err_banner.inner_text = AsyncMock(return_value="You have reached your limit")
        mock_page.query_selector = AsyncMock(return_value=err_banner)

        client = GeminiClient(mock_page)
        err = await client._detect_page_error()
        self.assertEqual(err, "You have reached your limit")

    async def test_gemini_client_detect_page_error_raises_in_send_message(self) -> None:
        mock_page = MagicMock()
        mock_page.is_closed = MagicMock(return_value=False)
        client = GeminiClient(mock_page)
        client._detect_page_error = AsyncMock(return_value="Usage limit exceeded")

        with self.assertRaises(RuntimeError) as cm:
            await client.send_message("hello")
        self.assertIn("Usage limit exceeded", str(cm.exception))

    async def test_gemini_client_generate_image(self) -> None:
        mock_page = MagicMock()
        client = GeminiClient(mock_page)
        fake_response = ChatResponse(
            message="Here is your image",
            has_images=True,
            images=[
                ImageInfo(
                    url="https://googleusercontent.com/img123",
                    local_path="/tmp/img123.png",
                    alt="A majestic lion",
                    prompt_title="Gemini Generated Image",
                )
            ],
        )
        client.send_message = AsyncMock(return_value=fake_response)

        resp = await client.generate_image("a majestic lion", n=1, size="1024x1024", style="vivid")
        self.assertTrue(resp.has_images)
        self.assertEqual(len(resp.images), 1)
        self.assertEqual(resp.images[0].url, "https://googleusercontent.com/img123")
        client.send_message.assert_awaited_once()
        sent_prompt = client.send_message.call_args[0][0]
        self.assertIn("Generate 1 image: a majestic lion", sent_prompt)
        self.assertIn("Aspect ratio: 1024x1024", sent_prompt)
        self.assertIn("Style: vivid", sent_prompt)

    async def test_gemini_client_extract_response_images(self) -> None:
        mock_page = MagicMock()
        response_root = AsyncMock()
        img_el = AsyncMock()
        img_el.is_visible = AsyncMock(return_value=True)
        img_el.get_attribute = AsyncMock(side_effect=lambda attr: {
            "src": "https://googleusercontent.com/chat_attachment_abc",
            "alt": "Generated picture",
        }.get(attr))
        mock_page.query_selector_all = AsyncMock(return_value=[response_root])
        response_root.query_selector_all = AsyncMock(return_value=[img_el])

        client = GeminiClient(mock_page)
        client._download_image = AsyncMock(return_value="/tmp/local_gemini_img.png")

        images = await client._extract_response_images()
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].url, "https://googleusercontent.com/chat_attachment_abc")
        self.assertEqual(images[0].local_path, "/tmp/local_gemini_img.png")
        self.assertEqual(images[0].alt, "Generated picture")

    async def test_gemini_long_prompt_error_mode_rejects_before_typing(self) -> None:
        mock_page = MagicMock()
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.click = AsyncMock()
        client = GeminiClient(mock_page)
        client._detect_page_error = AsyncMock(return_value=None)
        client._find_selector = AsyncMock(return_value="div.ql-editor")

        with (
            patch.object(Config, "GEMINI_LONG_PROMPT_THRESHOLD", 3),
            patch.object(Config, "GEMINI_LONG_PROMPT_FALLBACK", "error"),
            patch("src.gemini.client.random_delay", new=AsyncMock()),
            patch("src.gemini.client.count_assistant_messages", new=AsyncMock(return_value=0)),
            patch("src.gemini.client.get_latest_assistant_turn_signature", new=AsyncMock(return_value=None)),
            patch("src.gemini.client.human_type", new=AsyncMock()) as human_type_mock,
        ):
            with self.assertRaises(PromptTooLongError):
                await client.send_message("abcd")
        human_type_mock.assert_not_awaited()

    async def test_gemini_long_prompt_temp_file_is_cleaned_when_upload_fails(self) -> None:
        mock_page = MagicMock()
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.click = AsyncMock()
        client = GeminiClient(mock_page)
        client._detect_page_error = AsyncMock(return_value=None)
        client._find_selector = AsyncMock(return_value="div.ql-editor")
        captured_path = ""

        async def fail_upload(paths: list[str]) -> None:
            nonlocal captured_path
            captured_path = paths[-1]
            self.assertTrue(Path(captured_path).exists())
            raise PromptAttachmentFallbackError("upload failed")

        client._upload_files = fail_upload  # type: ignore[method-assign]
        with (
            patch.object(Config, "GEMINI_LONG_PROMPT_THRESHOLD", 3),
            patch.object(Config, "GEMINI_LONG_PROMPT_FALLBACK", "attachment"),
            patch("src.gemini.client.random_delay", new=AsyncMock()),
            patch("src.gemini.client.count_assistant_messages", new=AsyncMock(return_value=0)),
            patch("src.gemini.client.get_latest_assistant_turn_signature", new=AsyncMock(return_value=None)),
            patch("src.gemini.client.human_type", new=AsyncMock()),
        ):
            with self.assertRaises(PromptAttachmentFallbackError):
                await client.send_message("abcd")
        self.assertTrue(captured_path)
        self.assertFalse(Path(captured_path).exists())

    async def test_gemini_upload_rejects_missing_file(self) -> None:
        client = GeminiClient(MagicMock())
        missing = str(Path(tempfile.gettempdir()) / "catgpt-definitely-missing-attachment.txt")
        Path(missing).unlink(missing_ok=True)
        with self.assertRaises(PromptAttachmentFallbackError):
            await client._upload_files([missing])


if __name__ == "__main__":
    unittest.main()
