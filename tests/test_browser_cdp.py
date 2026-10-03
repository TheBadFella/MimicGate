from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.browser import manager


class BrowserCdpHelperTests(unittest.TestCase):
    def test_build_cdp_chrome_args_uses_dedicated_profile_and_port(self) -> None:
        chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        profile = Path(r"C:\Users\test\.mimicgate\browser_profile")

        args = manager._build_cdp_chrome_args(
            chrome,
            profile,
            9223,
            headless=False,
        )

        self.assertEqual(args[0], str(chrome))
        self.assertIn("--remote-debugging-port=9223", args)
        self.assertIn(f"--user-data-dir={profile}", args)
        self.assertIn("--remote-allow-origins=http://127.0.0.1:9223", args)
        self.assertNotIn("--headless=new", args)

    def test_cdp_metadata_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            manager._write_cdp_metadata(profile, 12345, 9223)

            self.assertEqual(manager._read_cdp_metadata(profile), (12345, 9223))

    def test_reuse_refreshes_windows_owner_pid(self) -> None:
        profile = Path(r"C:\Users\test\.mimicgate\browser_profile")

        with (
            patch.object(manager, "_read_cdp_metadata", return_value=(111, 9223)),
            patch.object(manager, "_pid_running", return_value=True),
            patch.object(manager, "_cdp_ready", return_value=True),
            patch.object(manager.platform, "system", return_value="Windows"),
            patch.object(manager, "_windows_profile_owner_pid", return_value=222),
            patch.object(manager, "_write_cdp_metadata") as write_metadata,
            patch.object(manager, "_cleanup_stale_locks") as cleanup,
        ):
            process, port, reused = manager._launch_or_reuse_cdp_chrome(
                profile,
                9223,
                channel="chrome",
                headless=False,
            )

        self.assertIsNone(process)
        self.assertEqual(port, 9223)
        self.assertTrue(reused)
        write_metadata.assert_called_once_with(profile, 222, 9223)
        cleanup.assert_not_called()

    def test_adopts_live_profile_before_cleaning_locks(self) -> None:
        profile = Path(r"C:\Users\test\.mimicgate\browser_profile")

        with (
            patch.object(manager, "_read_cdp_metadata", return_value=None),
            patch.object(manager, "_cdp_ready", return_value=True),
            patch.object(manager, "_windows_profile_owner_pid", return_value=333),
            patch.object(manager, "_pid_running", return_value=True),
            patch.object(manager, "_write_cdp_metadata") as write_metadata,
            patch.object(manager, "_cleanup_stale_locks") as cleanup,
        ):
            process, port, reused = manager._launch_or_reuse_cdp_chrome(
                profile,
                9223,
                channel="chrome",
                headless=False,
            )

        self.assertIsNone(process)
        self.assertEqual(port, 9223)
        self.assertTrue(reused)
        write_metadata.assert_called_once_with(profile, 333, 9223)
        cleanup.assert_not_called()


class BrowserCdpLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_does_not_close_reused_browser(self) -> None:
        browser = AsyncMock()
        playwright = AsyncMock()
        instance = manager.BrowserManager()
        instance._browser = browser
        instance._playwright = playwright
        instance._cdp_attached = True
        instance._cdp_reused = True

        with patch.object(manager, "_clear_cdp_metadata") as clear_metadata:
            await instance.close()

        browser.close.assert_not_awaited()
        playwright.stop.assert_awaited_once()
        clear_metadata.assert_not_called()


if __name__ == "__main__":
    unittest.main()
