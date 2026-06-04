from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from src.browser.auto_login import can_prompt_for_login, ensure_logged_in


class FakeBrowser:
    def __init__(self, logged_in: bool = False) -> None:
        self.logged_in = logged_in
        self.checks = 0

    async def is_logged_in(self) -> bool:
        self.checks += 1
        return self.logged_in


class AutoLoginTests(unittest.IsolatedAsyncioTestCase):
    def test_can_prompt_for_login_respects_false_override(self) -> None:
        with mock.patch.dict("os.environ", {"AUTO_LOGIN_INTERACTIVE": "false"}):
            self.assertFalse(can_prompt_for_login())

    def test_can_prompt_for_login_respects_true_override(self) -> None:
        with mock.patch.dict("os.environ", {"AUTO_LOGIN_INTERACTIVE": "true"}):
            self.assertTrue(can_prompt_for_login())

    async def test_non_interactive_login_required_does_not_prompt(self) -> None:
        browser = FakeBrowser(logged_in=False)
        with mock.patch.dict("os.environ", {"AUTO_LOGIN_INTERACTIVE": "false"}), \
                mock.patch("builtins.input", side_effect=AssertionError("input should not be called")), \
                redirect_stdout(io.StringIO()) as stdout:
            result = await ensure_logged_in(browser)

        self.assertFalse(result)
        self.assertEqual(browser.checks, 1)
        self.assertIn("API will keep running", stdout.getvalue())

    async def test_already_logged_in_returns_true_without_prompt(self) -> None:
        browser = FakeBrowser(logged_in=True)
        with mock.patch("builtins.input", side_effect=AssertionError("input should not be called")):
            result = await ensure_logged_in(browser)

        self.assertTrue(result)
        self.assertEqual(browser.checks, 1)


if __name__ == "__main__":
    unittest.main()
