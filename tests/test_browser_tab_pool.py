from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.api.browser_gate import BrowserTabPool, PageLease, acquire_browser_page, configure_tab_pool
from src.config import Config


class _FakePage:
    def __init__(self, url: str = "https://chatgpt.com") -> None:
        self.url = url
        self._closed = False

    def is_closed(self) -> bool:
        return self._closed

    async def goto(self, url: str, **_kwargs) -> None:
        self.url = url

    async def close(self) -> None:
        self._closed = True

    async def title(self) -> str:
        return f"Title: {self.url}"

    async def screenshot(self, **_kwargs) -> bytes:
        return b"\xff\xd8\xff\xe0\x00\x10JFIF"  # Minimal dummy JPEG header


class _FakeBrowser:
    def __init__(self) -> None:
        self.page = _FakePage("https://chatgpt.com")
        self.context = SimpleNamespace(pages=[self.page])

    async def new_page(self) -> _FakePage:
        page = _FakePage("about:blank")
        self.context.pages.append(page)
        return page


class BrowserTabPoolTests(unittest.TestCase):
    def test_same_session_reuses_tab(self) -> None:
        browser = _FakeBrowser()
        pool = BrowserTabPool(browser)

        async def _run() -> tuple[object, object]:
            async with pool.acquire("sess-a") as first:
                page_one = first.page
                first_turn = first.is_first_turn
            async with pool.acquire("sess-a") as second:
                return page_one, second.page, first_turn, second.is_first_turn

        page_one, page_two, first_turn, second_turn = asyncio.run(_run())
        self.assertIs(page_one, page_two)
        self.assertTrue(first_turn)
        self.assertFalse(second_turn)

    def test_fallback_uses_process_lock_when_pool_disabled(self) -> None:
        configure_tab_pool(None)

        async def _run() -> PageLease:
            async with acquire_browser_page("sess-a") as lease:
                return lease

        with patch.object(Config, "uses_browser", return_value=True):
            lease = asyncio.run(_run())
        self.assertIsNone(lease.page)
        self.assertFalse(lease.is_first_turn)

    def test_list_tabs_and_screenshot(self) -> None:
        browser = _FakeBrowser()
        pool = BrowserTabPool(browser)

        async def _run():
            # Acquire one worker session
            async with pool.acquire("sess-worker") as lease:
                worker_page = lease.page
                tabs = await pool.list_tabs()
                self.assertEqual(len(tabs), 2)
                self.assertTrue(tabs[0]["is_control"])
                self.assertEqual(tabs[1]["session_key"], "sess-worker")

                # Test screenshot capture
                img_bytes = await pool.capture_tab_screenshot(0)
                self.assertTrue(img_bytes.startswith(b"\xff\xd8"))

                # Out of range screenshot
                with self.assertRaises(IndexError):
                    await pool.capture_tab_screenshot(99)

        asyncio.run(_run())

    def test_close_tab_protects_control_tab(self) -> None:
        browser = _FakeBrowser()
        pool = BrowserTabPool(browser)

        async def _run():
            # Try closing control tab (index 0)
            with self.assertRaises(ValueError):
                await pool.close_tab_by_index(0)

            # Open a worker tab and close it
            async with pool.acquire("sess-b") as lease:
                pass

            tabs_before = await pool.list_tabs()
            self.assertEqual(len(tabs_before), 2)

            res = await pool.close_tab_by_index(1)
            self.assertEqual(res["status"], "closed")

            tabs_after = await pool.list_tabs()
            self.assertEqual(len(tabs_after), 1)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
