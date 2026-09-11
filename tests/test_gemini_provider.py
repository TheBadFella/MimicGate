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
            # Concrete models
            self.assertEqual(
                openai_routes._resolve_model_id("gemini-3.8-flash"),
                "gemini-3.8-flash",
            )
            self.assertEqual(
                openai_routes._resolve_model_id("gemini-3.1-pro"),
                "gemini-3.1-pro",
            )
            # Unsupported model raises 400
            with self.assertRaises(HTTPException) as ctx:
                openai_routes._resolve_model_id("unknown-nonexistent-model")
            self.assertEqual(ctx.exception.status_code, 400)

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


if __name__ == "__main__":
    unittest.main()
