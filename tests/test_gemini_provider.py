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
        with patch.object(Config, "PROVIDER", "gemini"), patch.object(openai_routes.Config, "PROVIDER", "gemini"):
            # Default / auto fallback
            self.assertEqual(
                openai_routes._resolve_model_id(None),
                Config.GEMINI_DEFAULT_MODEL,
            )
            self.assertEqual(
                openai_routes._resolve_model_id("gemini-browser"),
                Config.GEMINI_DEFAULT_MODEL,
            )
            self.assertEqual(
                openai_routes._resolve_model_id("catgpt-browser"),
                Config.GEMINI_DEFAULT_MODEL,
            )
            self.assertEqual(
                openai_routes._resolve_model_id("gpt-4o"),
                Config.GEMINI_DEFAULT_MODEL,
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
            # Unknown model falls back to default model gracefully
            self.assertEqual(
                openai_routes._resolve_model_id("unknown-nonexistent-model"),
                Config.GEMINI_DEFAULT_MODEL,
            )

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


if __name__ == "__main__":
    unittest.main()
