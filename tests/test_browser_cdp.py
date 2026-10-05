from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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

    def test_command_line_requires_exact_user_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile"
            other = Path(tmp) / "profile-other"
            profile.mkdir()
            other.mkdir()
            command = (
                f'chrome.exe --remote-debugging-port=9223 --user-data-dir="{other}"'
            )
            self.assertFalse(
                manager._command_line_owns_profile(command, profile, 9223)
            )
            exact = (
                f'chrome.exe --remote-debugging-port=9223 --user-data-dir="{profile}"'
            )
            self.assertTrue(manager._command_line_owns_profile(exact, profile, 9223))

    def test_command_line_accepts_edge_process_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "profile"
            profile.mkdir()
            command = (
                f'msedge.exe --remote-debugging-port=9223 --user-data-dir="{profile}"'
            )
            self.assertTrue(manager._command_line_owns_profile(command, profile, 9223))

    def test_reuse_requires_exact_owner_on_all_platforms(self) -> None:
        profile = Path(r"C:\Users\test\.mimicgate\browser_profile")

        with (
            patch.object(manager, "_read_cdp_metadata", return_value=(111, 9223)),
            patch.object(manager, "_pid_running", return_value=True),
            patch.object(manager, "_cdp_ready", return_value=True),
            patch.object(manager, "_pid_owns_profile", return_value=False),
            patch.object(manager, "_profile_owner_pid", return_value=222),
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

    def test_linux_metadata_reuse_rejects_unrelated_pid(self) -> None:
        profile = Path("/tmp/mimicgate-profile")

        with (
            patch.object(manager, "_read_cdp_metadata", return_value=(111, 9223)),
            patch.object(manager, "_pid_running", return_value=True),
            patch.object(manager, "_cdp_ready", return_value=True),
            patch.object(manager, "_pid_owns_profile", return_value=False),
            patch.object(manager, "_profile_owner_pid", return_value=None),
            patch.object(manager, "_clear_cdp_metadata") as clear_metadata,
            patch.object(manager, "_cleanup_stale_locks"),
            patch.object(manager, "_chrome_executable", return_value=Path("/usr/bin/google-chrome")),
            patch.object(manager, "_available_cdp_port", return_value=9224),
            patch.object(manager.subprocess, "Popen") as popen,
            patch.object(manager, "_write_cdp_metadata"),
            patch.object(manager.platform, "system", return_value="Linux"),
        ):
            process = MagicMock()
            process.poll.side_effect = [None] + [1] * 200
            popen.return_value = process
            with self.assertRaises(RuntimeError):
                manager._launch_or_reuse_cdp_chrome(
                    profile,
                    9223,
                    channel="chrome",
                    headless=False,
                )

        clear_metadata.assert_called()

    def test_adopts_live_profile_before_cleaning_locks(self) -> None:
        profile = Path(r"C:\Users\test\.mimicgate\browser_profile")

        with (
            patch.object(manager, "_read_cdp_metadata", return_value=None),
            patch.object(manager, "_cdp_ready", return_value=True),
            patch.object(manager, "_profile_owner_pid", return_value=333),
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

    async def test_failed_cdp_attach_terminates_launched_process(self) -> None:
        playwright = AsyncMock()
        playwright.chromium.connect_over_cdp = AsyncMock(
            side_effect=RuntimeError("connect failed")
        )
        process = MagicMock()
        process.poll.return_value = None

        instance = manager.BrowserManager()
        instance._playwright = playwright

        with (
            patch.object(
                manager,
                "_launch_or_reuse_cdp_chrome",
                return_value=(process, 9223, False),
            ),
            patch.object(manager, "_clear_cdp_metadata") as clear_metadata,
            patch.object(manager.Config, "BROWSER_DATA_DIR", Path("/tmp/profile")),
            patch.object(manager.Config, "BROWSER_CDP_PORT", 9223),
            patch.object(manager.Config, "BROWSER_CHANNEL", "chrome"),
            patch.object(manager.Config, "HEADLESS", False),
        ):
            with self.assertRaisesRegex(RuntimeError, "connect failed"):
                await instance._start_cdp_browser()

        clear_metadata.assert_called_once()
        process.terminate.assert_called_once()
        self.assertIsNone(instance._chrome_process)
        self.assertFalse(instance._cdp_attached)

    async def test_close_cleans_launched_process_even_without_attach(self) -> None:
        playwright = AsyncMock()
        process = MagicMock()
        process.poll.return_value = None
        process.wait.side_effect = TimeoutError()

        instance = manager.BrowserManager()
        instance._playwright = playwright
        instance._chrome_process = process
        instance._cdp_attached = False
        instance._cdp_reused = False

        with (
            patch.object(manager, "_clear_cdp_metadata") as clear_metadata,
            patch.object(manager.Config, "BROWSER_DATA_DIR", Path("/tmp/profile")),
        ):
            await instance.close()

        clear_metadata.assert_called_once()
        process.terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
