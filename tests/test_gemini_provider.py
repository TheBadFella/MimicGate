from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException

from src.api import openai_routes
from src.config import Config
from src.gemini.client import GeminiClient
from src.gemini.model_registry import PUBLIC_GEMINI_BROWSER_MODEL_ID


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


if __name__ == "__main__":
    unittest.main()
