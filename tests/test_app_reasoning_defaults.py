from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from src.api import openai_routes
from src.api.openai_schemas import (
    ChatCompletionAsyncRequest, ChatCompletionRequest, ChatMessage, ReasoningOptions, ResponsesRequest,
)
from src.chatgpt import model_registry
from src.chatgpt.errors import PromptTooLongError


class AppReasoningDefaultsTests(unittest.IsolatedAsyncioTestCase):
    def request(self, model: str = "gpt-5.6-sol", **kwargs) -> ChatCompletionRequest:
        return ChatCompletionRequest(model=model, messages=[ChatMessage(role="user", content="fixture")], **kwargs)

    def setUp(self) -> None:
        self.enterContext(patch.object(openai_routes.Config, "PROVIDER", "chatgpt"))
        self.enterContext(patch.object(openai_routes.Config, "CHATGPT_APP_REASONING_EFFORTS",
                                      "karakeep=medium,paperlessgpt=high"))
        self.enterContext(patch.object(model_registry.Config, "CHATGPT_DEFAULT_MODEL", ""))

    def test_endpoint_defaults_and_unscoped_fallback(self) -> None:
        request = self.request()
        for key, expected in (("endpoint:karakeep", "medium"), ("endpoint:paperlessgpt", "high"),
                              ("endpoint:unknown", None), ("user:karakeep", None), ("", None)):
            with self.subTest(key=key):
                self.assertEqual(openai_routes._chat_reasoning_effort(request, key), expected)

    def test_explicit_fields_and_legacy_ids_keep_precedence(self) -> None:
        key = "endpoint:karakeep"
        self.assertEqual(openai_routes._chat_reasoning_effort(self.request(reasoning_effort="low"), key), "low")
        self.assertEqual(openai_routes._chat_reasoning_effort(
            self.request(reasoning=ReasoningOptions(effort="high")), key), "high")
        for model in ("gpt-5.6-sol-high", "gpt-5.5-thinking", "gpt-6.1:high", "gpt-5.6-sol-pro", "Instant"):
            with self.subTest(model=model):
                self.assertIsNone(openai_routes._chat_reasoning_effort(self.request(model), key))

    def test_browser_alias_uses_default_without_changing_selected_model(self) -> None:
        self.assertEqual(openai_routes._chat_reasoning_effort(self.request("mimicgate-browser"), "endpoint:karakeep"), "medium")
        with patch.object(model_registry.Config, "CHATGPT_DEFAULT_MODEL", "gpt-5.6-sol-high"):
            self.assertIsNone(openai_routes._chat_reasoning_effort(self.request("catgpt-browser"), "endpoint:karakeep"))

    def test_other_providers_do_not_use_chatgpt_defaults(self) -> None:
        with patch.object(openai_routes.Config, "PROVIDER", "gemini"):
            self.assertIsNone(openai_routes._chat_reasoning_effort(self.request("gemini-browser"), "endpoint:karakeep"))

    def test_responses_defaults_preserve_options_and_leave_original_unchanged(self) -> None:
        request = ResponsesRequest(model="gpt-5.6-sol", input="fixture", reasoning=ReasoningOptions(summary="auto"))
        updated = openai_routes._with_app_reasoning_default(request, "PaperlessGPT")
        self.assertEqual(updated.reasoning.effort, "high")
        self.assertEqual(updated.reasoning.summary, "auto")
        self.assertIsNone(request.reasoning.effort)

    async def test_streaming_scoped_routes_receive_defaults_without_app_threads(self) -> None:
        http_request = Request({"type": "http", "headers": []})
        with patch.object(openai_routes.Config, "API_APP_THREAD_MODE", False), patch.object(
            openai_routes, "_stream_chat_completion", new_callable=AsyncMock,
        ) as stream:
            await openai_routes.create_chat_completion_scoped("karakeep", self.request(stream=True), http_request)
            self.assertEqual(stream.call_args.args[0].reasoning_effort, "medium")
        with patch.object(openai_routes.Config, "API_APP_THREAD_MODE", False), patch.object(
            openai_routes, "_stream_responses", new_callable=AsyncMock,
        ) as stream:
            request = ResponsesRequest(model="gpt-5.6-sol", input="fixture", stream=True)
            await openai_routes.create_responses_scoped("paperlessgpt", request, http_request)
            self.assertEqual(stream.call_args.args[0].reasoning.effort, "high")

    async def test_async_submission_retains_url_default(self) -> None:
        request = ChatCompletionAsyncRequest(model="gpt-5.6-sol", messages=[ChatMessage(role="user", content="fixture")])
        with patch.object(openai_routes.Config, "API_APP_THREAD_MODE", False), patch.object(
            openai_routes, "_get_client", return_value=object(),
        ), patch.object(openai_routes, "_run_async_chat_job", new_callable=AsyncMock) as run:
            job = await openai_routes._submit_async_chat_job(
                request, Request({"type": "http", "headers": []}), endpoint_app_name="paperlessgpt",
            )
            try:
                await asyncio.sleep(0)
                self.assertEqual(run.call_args.args[1].reasoning_effort, "high")
                self.assertIsNone(request.reasoning_effort)
            finally:
                openai_routes._jobs.pop(job.id, None)
                openai_routes._job_app_keys.pop(job.id, None)

    def test_app_efforts_partition_cache_when_app_threads_are_disabled(self) -> None:
        with patch.object(openai_routes.Config, "API_APP_THREAD_MODE", False):
            request = self.request()
            requests = [openai_routes._with_app_reasoning_default(request, app)
                        for app in ("karakeep", "paperlessgpt", "unknown")]
            keys = [openai_routes._cache_key_for_request_with_app(req, "") for req in requests]
            self.assertEqual(len(set(keys)), 3)

    def test_configuration_normalizes_names_and_rejects_mistakes(self) -> None:
        with patch.object(openai_routes.Config, "CHATGPT_APP_REASONING_EFFORTS", " Karakeep = Medium , paperlessgpt=extra-high "):
            self.assertEqual(openai_routes.Config.chatgpt_app_reasoning_efforts(),
                             {"karakeep": "medium", "paperlessgpt": "xhigh"})
        for value in ("karakeep", "=high", "karakeep=typo", "karakeep=", "kara keep=high",
                      "karakeep=low,Karakeep=high"):
            with self.subTest(value=value), patch.object(openai_routes.Config, "CHATGPT_APP_REASONING_EFFORTS", value):
                with self.assertRaisesRegex(ValueError, "CHATGPT_APP_REASONING_EFFORTS"):
                    openai_routes.Config.validate_provider()

    async def test_scoped_route_passes_app_effort_to_client(self) -> None:
        received = {}

        class Client(openai_routes.ChatGPTClient):
            def __init__(self):
                super().__init__(SimpleNamespace(url="https://chatgpt.com"))

            async def send_message(self, *_args, **kwargs):
                received.update(kwargs)
                raise PromptTooLongError("fixture")

        @asynccontextmanager
        async def lease(_session):
            yield SimpleNamespace(page=object())

        client = Client()
        with (
            patch.object(openai_routes, "_get_client", return_value=client),
            patch.object(openai_routes, "_bind_client", return_value=client),
            patch.object(openai_routes, "acquire_browser_page", lease),
            patch.object(openai_routes, "_tab_session_key", return_value=""),
            patch.object(openai_routes.Config, "API_APP_THREAD_MODE", False),
            patch.object(openai_routes.Config, "uses_browser", return_value=False),
        ):
            with self.assertRaises(HTTPException) as error:
                await openai_routes.create_chat_completion_scoped(
                    "paperlessgpt", self.request(), Request({"type": "http", "headers": []}),
                )
        self.assertEqual(error.exception.status_code, 413)
        self.assertEqual(received["reasoning_effort"], "high")
        self.assertEqual(received["model"], "gpt-5.6-sol")


if __name__ == "__main__":
    unittest.main()
