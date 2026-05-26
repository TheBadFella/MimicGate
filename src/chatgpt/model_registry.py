"""
Model registry helpers for browser-backed ChatGPT model switching.

Maps public API model ids to the visible labels shown in ChatGPT's model picker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.config import Config

PUBLIC_BROWSER_MODEL_ID = "catgpt-browser"
_AUTO_MODEL_IDS = {
    "",
    "auto",
    "default",
    "browser",
    PUBLIC_BROWSER_MODEL_ID,
}


@dataclass(frozen=True)
class BrowserModelOption:
    """A public API model id paired with the ChatGPT UI label to click."""

    public_id: str
    ui_label: str
    alternate_labels: tuple[str, ...] = ()

    @property
    def ui_labels(self) -> tuple[str, ...]:
        """All visible labels that may identify this model in ChatGPT's UI."""
        return (self.ui_label, *self.alternate_labels)


def normalize_model_token(value: str) -> str:
    """Normalize model ids / labels for resilient matching."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower())


def _parse_model_aliases(raw: str) -> list[BrowserModelOption]:
    """Parse a comma-separated alias list like `gpt-5.3=GPT-5.3,o3=o3`."""
    options: list[BrowserModelOption] = []
    seen: set[str] = set()

    for chunk in (raw or "").split(","):
        item = chunk.strip()
        if not item:
            continue

        if "=" in item:
            public_id, labels = item.split("=", 1)
        else:
            public_id, labels = item, item

        public_id = public_id.strip()
        parsed_labels = tuple(label.strip() for label in labels.split("|") if label.strip())
        ui_label = parsed_labels[0] if parsed_labels else ""
        alternate_labels = parsed_labels[1:]
        normalized = normalize_model_token(public_id)
        if not public_id or not ui_label or not normalized or normalized in seen:
            continue

        options.append(
            BrowserModelOption(
                public_id=public_id,
                ui_label=ui_label,
                alternate_labels=alternate_labels,
            )
        )
        seen.add(normalized)

    return options


def list_switchable_models() -> list[BrowserModelOption]:
    """Return the configured explicit browser-switchable models."""
    return _parse_model_aliases(Config.CHATGPT_MODEL_ALIASES)


def list_public_chat_models() -> list[str]:
    """Return public model ids exposed via `/v1/models`."""
    model_ids = [PUBLIC_BROWSER_MODEL_ID]
    model_ids.extend(option.public_id for option in list_switchable_models())
    return model_ids


def is_supported_chat_model(model: str) -> bool:
    """Return whether a request model is supported by the browser gateway."""
    normalized = normalize_model_token(model)
    if normalized in {normalize_model_token(v) for v in _AUTO_MODEL_IDS}:
        return True

    for option in list_switchable_models():
        labels = {normalize_model_token(label) for label in option.ui_labels}
        if normalized in {normalize_model_token(option.public_id), *labels}:
            return True

    return False


def resolve_requested_model(model: str) -> BrowserModelOption | None:
    """
    Resolve the requested public model id to a ChatGPT UI label.

    `catgpt-browser` and other auto aliases only trigger a model switch when
    `CHATGPT_DEFAULT_MODEL` is configured to one of the explicit models.
    """
    normalized = normalize_model_token(model)
    if normalized in {normalize_model_token(v) for v in _AUTO_MODEL_IDS}:
        default_model = (Config.CHATGPT_DEFAULT_MODEL or "").strip()
        if not default_model:
            return None
        normalized = normalize_model_token(default_model)

    for option in list_switchable_models():
        labels = {normalize_model_token(label) for label in option.ui_labels}
        if normalized in {normalize_model_token(option.public_id), *labels}:
            return option

    return None

