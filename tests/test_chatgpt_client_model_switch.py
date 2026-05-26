from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

# Provide a minimal patchright stub so client tests can import browser modules
# without requiring browser automation dependencies.
if "patchright" not in sys.modules:
    patchright_mod = types.ModuleType("patchright")
    async_api_mod = types.ModuleType("patchright.async_api")
    async_api_mod.Page = object
    sys.modules["patchright"] = patchright_mod
    sys.modules["patchright.async_api"] = async_api_mod

if "pydantic" not in sys.modules:
    pydantic_mod = types.ModuleType("pydantic")

    class _BaseModel:
        def __init__(self, **kwargs) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    _missing = object()

    def _Field(default=_missing, default_factory=None, **_kwargs):
        if default_factory is not None:
            return default_factory()
        if default is _missing:
            return None
        return default

    pydantic_mod.BaseModel = _BaseModel
    pydantic_mod.Field = _Field
    sys.modules["pydantic"] = pydantic_mod

from src.chatgpt.client import ChatGPTClient
from src.config import Config


async def _noop_sleep(*_args, **_kwargs) -> None:
    return None


class _FakeKeyboard:
    def __init__(self) -> None:
        self.presses: list[str] = []

    async def press(self, key: str) -> None:
        self.presses.append(key)


class _FakeMouse:
    def __init__(self) -> None:
        self.clicks: list[tuple[float, float]] = []

    async def move(self, _x: float, _y: float, **_kwargs) -> None:
        return None

    async def click(self, x: float, y: float) -> None:
        self.clicks.append((x, y))


class _FakePage:
    def __init__(self, open_picker: bool = False, visible_options: list[str] | None = None) -> None:
        self.keyboard = _FakeKeyboard()
        self.mouse = _FakeMouse()
        self.open_picker = open_picker
        self.visible_options = visible_options or []
        self.evaluate_calls: list[object] = []
        self.wait_for_selector_calls = 0

    async def wait_for_selector(self, *_args, **_kwargs):
        self.wait_for_selector_calls += 1
        raise RuntimeError("selector unavailable")

    async def evaluate(self, _script: str, arg=None):
        self.evaluate_calls.append(arg)

        if isinstance(arg, list):
            # _click_top_button_by_text includes generic picker hints.
            if "Configure" in arg or "model" in arg:
                return {"x": 100, "y": 100} if self.open_picker else None
            # _detect_current_model_label passes configured model labels.
            return ""

        # _click_menu_text passes a string target and should not find one here.
        if isinstance(arg, str):
            return False

        # _collect_visible_model_options passes no arg.
        return self.visible_options


class ChatGPTClientModelSwitchTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_model_option_falls_back_and_caches_when_not_strict(self) -> None:
        page = _FakePage(open_picker=True, visible_options=["GPT-5", "o3"])
        client = ChatGPTClient(page)  # type: ignore[arg-type]

        with patch.object(Config, "CHATGPT_MODEL_SWITCH_STRICT", False), patch(
            "src.chatgpt.client.asyncio.sleep",
            _noop_sleep,
        ):
            await client.ensure_model("gpt-5.5")
            evaluate_calls_after_first_attempt = len(page.evaluate_calls)
            await client.ensure_model("gpt-5.5")

        self.assertIn("gpt55", client._unavailable_model_keys)
        self.assertEqual(len(page.evaluate_calls), evaluate_calls_after_first_attempt)
        self.assertEqual(page.keyboard.presses, ["Escape", "Escape"])

    async def test_model_picker_open_failure_raises_when_strict(self) -> None:
        page = _FakePage(open_picker=False)
        client = ChatGPTClient(page)  # type: ignore[arg-type]

        with patch.object(Config, "CHATGPT_MODEL_SWITCH_STRICT", True), patch(
            "src.chatgpt.client.asyncio.sleep",
            _noop_sleep,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                await client.ensure_model("gpt-5.5")

        self.assertIn("Could not open ChatGPT model picker", str(ctx.exception))
        self.assertEqual(page.keyboard.presses, ["Escape", "Escape"])


if __name__ == "__main__":
    unittest.main()
