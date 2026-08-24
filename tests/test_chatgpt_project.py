from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from src.chatgpt.client import ChatGPTClient
from src.config import Config


PROJECT_URL = "https://chatgpt.com/g/g-p-example-catgpt/project"


class _ProjectPage:
    def __init__(self, url: str, turns: int = 0) -> None:
        self.url = url
        self.turns = turns
        self.goto_calls: list[str] = []
        self.wait_calls: list[str] = []
        self.on = lambda *_args, **_kwargs: None

    async def evaluate(self, _script: str):
        return self.turns

    async def goto(self, url: str, **_kwargs):
        self.goto_calls.append(url)
        self.url = url

    async def wait_for_selector(self, selector: str, **_kwargs):
        self.wait_calls.append(selector)
        return object()


class ChatGPTProjectTests(unittest.IsolatedAsyncioTestCase):
    def test_project_url_validation(self) -> None:
        with patch.object(Config, "CHATGPT_PROJECT_URL", PROJECT_URL + "/"):
            self.assertEqual(Config.chatgpt_project_url(), PROJECT_URL)
        with patch.object(Config, "CHATGPT_PROJECT_URL", "https://example.com/project"):
            with self.assertRaises(ValueError):
                Config.chatgpt_project_url()

    async def test_global_fresh_page_navigates_to_configured_project(self) -> None:
        page = _ProjectPage("https://chatgpt.com/", turns=0)
        client = ChatGPTClient(page)  # type: ignore[arg-type]
        client._detect_page_error = AsyncMock(return_value=None)
        with patch.object(Config, "CHATGPT_PROJECT_URL", PROJECT_URL):
            await client.new_chat()
        self.assertEqual(page.goto_calls, [PROJECT_URL])

    async def test_project_root_is_reused_as_fresh_chat(self) -> None:
        page = _ProjectPage(PROJECT_URL, turns=0)
        client = ChatGPTClient(page)  # type: ignore[arg-type]
        with patch.object(Config, "CHATGPT_PROJECT_URL", PROJECT_URL):
            await client.new_chat()
        self.assertEqual(page.goto_calls, [])

    async def test_thread_navigation_uses_project_scoped_path(self) -> None:
        page = _ProjectPage(PROJECT_URL)
        client = ChatGPTClient(page)  # type: ignore[arg-type]
        with patch.object(Config, "CHATGPT_PROJECT_URL", PROJECT_URL), patch(
            "src.chatgpt.client.random_delay", AsyncMock()
        ):
            await client.navigate_to_thread("abc-123")
        self.assertEqual(
            page.goto_calls,
            ["https://chatgpt.com/g/g-p-example-catgpt/c/abc-123"],
        )

    def test_project_scope_rejects_global_conversation(self) -> None:
        page = _ProjectPage("https://chatgpt.com/c/abc-123")
        client = ChatGPTClient(page)  # type: ignore[arg-type]
        with patch.object(Config, "CHATGPT_PROJECT_URL", PROJECT_URL):
            with self.assertRaisesRegex(RuntimeError, "outside the configured project"):
                client._verify_project_thread_scope("abc-123")


if __name__ == "__main__":
    unittest.main()
