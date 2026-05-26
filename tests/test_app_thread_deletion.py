"""Tests for app-thread expiry and optional ChatGPT thread deletion.

Fastapi and starlette are stubbed before import and restored after,
so other test modules are not polluted.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import time
import unittest
import unittest.mock
from types import SimpleNamespace

_MISSING_FASTAPI_MODULES = (
    "fastapi",
    "fastapi.exceptions",
    "fastapi.params",
    "fastapi.routing",
    "fastapi.applications",
    "fastapi.openapi",
    "fastapi.middleware",
    "starlette",
    "starlette.requests",
    "starlette.responses",
    "starlette.routing",
    "starlette.status",
)


def _stub_fastapi():
    """Replace missing fastapi/starlette modules with MagicMock."""
    for mod in _MISSING_FASTAPI_MODULES:
        if mod not in sys.modules:
            sys.modules[mod] = unittest.mock.MagicMock()


def _restore_fastapi():
    """Remove fastapi/starlette stubs from sys.modules."""
    for mod in _MISSING_FASTAPI_MODULES:
        m = sys.modules.get(mod)
        if isinstance(m, unittest.mock.MagicMock):
            del sys.modules[mod]


def _fresh_openai_routes():
    """Return a freshly-imported openai_routes module with fastapi stubs isolated."""
    _stub_fastapi()
    try:
        # Force re-import so any prior partial imports are discarded.
        import src.api.openai_routes
        importlib.reload(src.api.openai_routes)
        return src.api.openai_routes
    finally:
        _restore_fastapi()


class TestAppThreadDeletionConfig(unittest.TestCase):
    """Config default and flag behavior tests."""

    def test_default_is_false(self):
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            import src.config
            importlib.reload(src.config)
            from src.config import Config as FreshConfig
            self.assertFalse(FreshConfig.API_APP_THREAD_DELETE_EXPIRED)

    def test_explicit_true(self):
        with unittest.mock.patch.dict("os.environ", {"API_APP_THREAD_DELETE_EXPIRED": "true"}, clear=True):
            import src.config
            importlib.reload(src.config)
            from src.config import Config as FreshConfig
            self.assertTrue(FreshConfig.API_APP_THREAD_DELETE_EXPIRED)


class TestPruneExpiredMappings(unittest.TestCase):
    """Pruning identifies expired app-thread mappings."""

    def test_returns_expired_thread_ids(self):
        routes = _fresh_openai_routes()
        _app_threads = routes._app_threads
        _prune_app_threads = routes._prune_app_threads

        _app_threads.clear()
        now = time.time()
        _app_threads["app1"] = routes._AppThreadMapping(now - 301, "thread-abc", created_by_catgpt=True)
        _app_threads["app2"] = routes._AppThreadMapping(now - 10, "thread-def", created_by_catgpt=True)

        with unittest.mock.patch.object(routes, "_APP_THREAD_TTL_SECONDS", 300):
            expired = _prune_app_threads(now)

        self.assertIn("thread-abc", expired)
        self.assertNotIn("thread-def", expired)
        self.assertNotIn("app1", _app_threads)
        self.assertIn("app2", _app_threads)
        _app_threads.clear()

    def test_deduplicates_thread_ids(self):
        routes = _fresh_openai_routes()
        _app_threads = routes._app_threads
        _prune_app_threads = routes._prune_app_threads

        _app_threads.clear()
        now = time.time()
        _app_threads["app1"] = routes._AppThreadMapping(now - 301, "thread-xyz", created_by_catgpt=True)
        _app_threads["app2"] = routes._AppThreadMapping(now - 301, "thread-xyz", created_by_catgpt=True)

        with unittest.mock.patch.object(routes, "_APP_THREAD_TTL_SECONDS", 300):
            expired = _prune_app_threads(now)

        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0], "thread-xyz")
        _app_threads.clear()

    def test_does_not_return_non_catgpt_created_thread_ids(self):
        routes = _fresh_openai_routes()
        _app_threads = routes._app_threads
        _prune_app_threads = routes._prune_app_threads

        _app_threads.clear()
        now = time.time()
        _app_threads["manual"] = routes._AppThreadMapping(
            now - 301,
            "manual-thread",
            created_by_catgpt=False,
        )

        with unittest.mock.patch.object(routes, "_APP_THREAD_TTL_SECONDS", 300):
            expired = _prune_app_threads(now)

        self.assertEqual([], expired)
        self.assertNotIn("manual", _app_threads)
        _app_threads.clear()


class TestMaybeDeleteExpiredAppThreads(unittest.TestCase):
    """Deletion helper behavior tests."""

    def test_skipped_when_flag_false(self):
        from src.config import Config

        routes = _fresh_openai_routes()
        _maybe_delete = routes._maybe_delete_expired_app_threads

        with unittest.mock.patch.object(Config, "API_APP_THREAD_DELETE_EXPIRED", False, create=True):
            with unittest.mock.patch.object(routes, "_get_client") as mock_get_client:
                mock_client = unittest.mock.MagicMock()
                mock_client.delete_thread = unittest.mock.AsyncMock()
                mock_get_client.return_value = mock_client

                asyncio.run(_maybe_delete(["thread-1"]))

            mock_client.delete_thread.assert_not_called()

    def test_attempted_when_flag_true(self):
        from src.chatgpt.client import ChatGPTClient
        from src.config import Config

        routes = _fresh_openai_routes()
        _maybe_delete = routes._maybe_delete_expired_app_threads

        with unittest.mock.patch.object(Config, "API_APP_THREAD_DELETE_EXPIRED", True, create=True):
            with unittest.mock.patch.object(routes, "_get_client") as mock_get_client:
                mock_client = unittest.mock.MagicMock(spec=ChatGPTClient)
                mock_client.delete_thread = unittest.mock.AsyncMock(return_value=True)
                mock_get_client.return_value = mock_client

                asyncio.run(_maybe_delete(["thread-abc"]))

            mock_client.delete_thread.assert_called_once_with("thread-abc")

    def test_deletion_failure_is_swallowed(self):
        from src.chatgpt.client import ChatGPTClient
        from src.config import Config

        routes = _fresh_openai_routes()
        _maybe_delete = routes._maybe_delete_expired_app_threads

        with unittest.mock.patch.object(Config, "API_APP_THREAD_DELETE_EXPIRED", True, create=True):
            with unittest.mock.patch.object(routes, "_get_client") as mock_get_client:
                mock_client = unittest.mock.MagicMock(spec=ChatGPTClient)
                mock_client.delete_thread = unittest.mock.AsyncMock(
                    side_effect=RuntimeError("simulated error")
                )
                mock_get_client.return_value = mock_client

                # Should not raise
                asyncio.run(_maybe_delete(["thread-1"]))

    def test_noop_when_thread_ids_empty(self):
        routes = _fresh_openai_routes()
        _maybe_delete = routes._maybe_delete_expired_app_threads

        with unittest.mock.patch.object(routes, "_get_client") as mock_get_client:
            asyncio.run(_maybe_delete([]))
            mock_get_client.assert_not_called()

    def test_noop_when_client_not_available(self):
        from src.config import Config

        routes = _fresh_openai_routes()
        _maybe_delete = routes._maybe_delete_expired_app_threads

        with unittest.mock.patch.object(Config, "API_APP_THREAD_DELETE_EXPIRED", True, create=True):
            with unittest.mock.patch.object(routes, "_get_client") as mock_get_client:
                mock_get_client.side_effect = Exception("503: not ready")

                # Should not raise
                asyncio.run(_maybe_delete(["thread-1"]))


class TestAppThreadDeletionOrdering(unittest.TestCase):
    """Regression tests for browser lock and cleanup scheduling order."""

    def test_send_message_runs_inside_browser_lock_and_cleanup_is_deferred(self):
        routes = _fresh_openai_routes()
        from src.api.openai_schemas import ChatCompletionRequest, ChatMessage
        from src.config import Config

        routes._app_threads.clear()
        routes._response_cache.clear()
        routes._thread_titles.clear()
        routes._app_threads["expired-app"] = routes._AppThreadMapping(
            time.time() - 301,
            "expired-thread",
            created_by_catgpt=True,
        )

        request = ChatCompletionRequest(
            model="catgpt-browser",
            messages=[ChatMessage(role="user", content="hello")],
        )

        send_lock_states: list[bool] = []
        scheduled_lock_states: list[bool] = []

        class FakeClient:
            def _extract_thread_id(self):
                return "new-thread"

            async def new_chat(self):
                return None

            async def send_message(self, *_args, **_kwargs):
                send_lock_states.append(routes.browser_access_lock.locked())
                if scheduled_lock_states:
                    raise AssertionError("cleanup was scheduled before send_message completed")
                return SimpleNamespace(message="ok", thread_id="new-thread", audio=None)

        def fake_create_task(coro):
            scheduled_lock_states.append(routes.browser_access_lock.locked())
            coro.close()
            return SimpleNamespace()

        async def run_request():
            with unittest.mock.patch.object(Config, "API_APP_THREAD_MODE", True, create=True), \
                 unittest.mock.patch.object(routes, "_APP_THREAD_TTL_SECONDS", 300), \
                 unittest.mock.patch.object(routes, "_get_client", return_value=FakeClient()), \
                 unittest.mock.patch.object(routes, "_lookup_thread_title", new=unittest.mock.AsyncMock(return_value="New thread")), \
                 unittest.mock.patch.object(routes.asyncio, "create_task", side_effect=fake_create_task):
                return await routes._execute_chat_completion(request, app_key_override="endpoint:test-app")

        response = asyncio.run(run_request())

        self.assertEqual("ok", response.choices[0].message.content)
        self.assertEqual([True], send_lock_states)
        self.assertEqual([False], scheduled_lock_states)
        self.assertTrue(routes._app_threads["endpoint:test-app"].created_by_catgpt)

    def test_explicit_thread_mapping_is_not_delete_owned(self):
        routes = _fresh_openai_routes()
        from src.api.openai_schemas import ChatCompletionRequest, ChatMessage
        from src.config import Config

        routes._app_threads.clear()
        routes._response_cache.clear()
        explicit_thread_id = "manual-thread"

        request = ChatCompletionRequest(
            model="catgpt-browser",
            messages=[ChatMessage(role="user", content="hello")],
            thread_id=explicit_thread_id,
        )

        class FakeClient:
            def _extract_thread_id(self):
                return explicit_thread_id

            async def navigate_to_thread(self, _thread_id):
                return None

            async def send_message(self, *_args, **_kwargs):
                return SimpleNamespace(message="ok", thread_id=explicit_thread_id, audio=None)

        async def run_request():
            with unittest.mock.patch.object(Config, "API_APP_THREAD_MODE", True, create=True), \
                 unittest.mock.patch.object(routes, "_get_client", return_value=FakeClient()), \
                 unittest.mock.patch.object(routes, "_lookup_thread_title", new=unittest.mock.AsyncMock(return_value="Manual thread")):
                return await routes._execute_chat_completion(request, app_key_override="endpoint:test-app")

        response = asyncio.run(run_request())

        self.assertEqual("ok", response.choices[0].message.content)
        mapping = routes._app_threads["endpoint:test-app"]
        self.assertEqual(explicit_thread_id, mapping.thread_id)
        self.assertFalse(mapping.created_by_catgpt)


class TestDeleteThreadMethod(unittest.TestCase):
    """Tests for ChatGPTClient.delete_thread (method signature check)."""

    def test_method_exists(self):
        from src.chatgpt.client import ChatGPTClient

        self.assertTrue(hasattr(ChatGPTClient, "delete_thread"))
        self.assertTrue(callable(getattr(ChatGPTClient, "delete_thread", None)))

    def test_delete_thread_does_not_click_global_menu_fallback(self):
        from src.chatgpt.client import ChatGPTClient

        thread_id = "abc123"
        parent = unittest.mock.MagicMock()
        parent.query_selector = unittest.mock.AsyncMock(return_value=None)

        thread_el = unittest.mock.MagicMock()
        thread_el.get_attribute = unittest.mock.AsyncMock(return_value=f"/c/{thread_id}")
        thread_el.hover = unittest.mock.AsyncMock()
        thread_el.evaluate_handle = unittest.mock.AsyncMock(return_value=parent)

        page = unittest.mock.MagicMock()
        page.query_selector_all = unittest.mock.AsyncMock(return_value=[thread_el])
        page.query_selector = unittest.mock.AsyncMock()

        client = ChatGPTClient(page)
        client.navigate_to_thread = unittest.mock.AsyncMock()

        async def run_delete():
            with unittest.mock.patch("src.chatgpt.client.asyncio.sleep", new=unittest.mock.AsyncMock()):
                return await client.delete_thread(thread_id)

        deleted = asyncio.run(run_delete())

        self.assertFalse(deleted)
        page.query_selector.assert_not_called()


if __name__ == "__main__":
    unittest.main()
