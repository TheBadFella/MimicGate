"""ChatGPT integration package."""

from __future__ import annotations

__all__ = ["ChatGPTClient"]


def __getattr__(name: str):
    if name == "ChatGPTClient":
        from src.chatgpt.client import ChatGPTClient

        return ChatGPTClient
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
