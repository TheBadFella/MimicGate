"""Browser automation package."""

from __future__ import annotations

__all__ = ["Browser"]


def __getattr__(name: str):
    if name == "Browser":
        from src.browser.manager import BrowserManager as Browser

        return Browser
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
