"""
Model registry helpers for browser-backed Gemini model switching.

Maps public API model IDs (e.g. gemini-3.8-flash, gemini-3.1-pro) to the visible
labels shown in Gemini'\''s model picker (<bard-mode-switcher>).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PUBLIC_GEMINI_BROWSER_MODEL_ID = "gemini-browser"

_AUTO_MODEL_IDS = {
    "",
    "auto",
    "default",
    "browser",
    "gemini",
    PUBLIC_GEMINI_BROWSER_MODEL_ID,
    "catgpt-browser",
    "claude-browser",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4",
    "gpt-3.5-turbo",
}


def is_auto_model(model_id: str | None) -> bool:
    """Return True if the requested model means 'use default browser model'."""
    if not model_id:
        return True
    return model_id.strip().lower() in _AUTO_MODEL_IDS


@dataclass(frozen=True)
class GeminiModelOption:
    """A public API model ID paired with the Gemini UI label to select."""

    public_id: str
    ui_label: str
    alternate_labels: tuple[str, ...] = ()

    @property
    def ui_labels(self) -> tuple[str, ...]:
        return (self.ui_label, *self.alternate_labels)


# Standard default registry based on live browser captures
DEFAULT_GEMINI_MODELS: tuple[GeminiModelOption, ...] = (
    GeminiModelOption(
        public_id="gemini-3.8-flash",
        ui_label="3.8 Flash",
        alternate_labels=("Flash", "3.6 Flash", "Fastest answers", "All-around help"),
    ),
    GeminiModelOption(
        public_id="gemini-3.6-flash",
        ui_label="3.6 Flash",
        alternate_labels=("Flash", "3.8 Flash", "All-around help"),
    ),
    GeminiModelOption(
        public_id="gemini-3.5-flash-lite",
        ui_label="3.5 Flash-Lite",
        alternate_labels=("Flash-Lite", "Flash Lite", "Fastest answers"),
    ),
    GeminiModelOption(
        public_id="gemini-3.1-pro",
        ui_label="3.1 Pro",
        alternate_labels=("Pro", "Advanced reasoning", "Gemini Advanced", "Advanced"),
    ),
    GeminiModelOption(
        public_id="gemini-extended-thinking",
        ui_label="Extended thinking",
        alternate_labels=("Thinking", "Complex problem solving"),
    ),
    # Aliases
    GeminiModelOption(
        public_id="gemini-flash",
        ui_label="Flash",
        alternate_labels=("3.8 Flash", "3.6 Flash"),
    ),
    GeminiModelOption(
        public_id="gemini-pro",
        ui_label="3.1 Pro",
        alternate_labels=("Pro", "Advanced reasoning"),
    ),
    GeminiModelOption(
        public_id="gemini-2.0-flash",
        ui_label="Flash",
        alternate_labels=("3.8 Flash", "3.6 Flash"),
    ),
    GeminiModelOption(
        public_id="gemini-1.5-flash",
        ui_label="Flash",
        alternate_labels=("3.8 Flash", "3.6 Flash"),
    ),
    GeminiModelOption(
        public_id="gemini-1.5-pro",
        ui_label="3.1 Pro",
        alternate_labels=("Pro",),
    ),
)


def normalize_token(value: str) -> str:
    """Normalize model tokens for resilient comparison."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower())


def list_gemini_model_ids() -> tuple[str, ...]:
    """Return all public model IDs supported by the Gemini provider."""
    return (PUBLIC_GEMINI_BROWSER_MODEL_ID,) + tuple(m.public_id for m in DEFAULT_GEMINI_MODELS)


def resolve_gemini_model(requested_model: str | None) -> GeminiModelOption | None:
    """
    Resolve a requested model ID to a GeminiModelOption.
    Returns None if the requested model means 'use whatever is currently selected in browser'.
    """
    if not requested_model or requested_model.strip().lower() in _AUTO_MODEL_IDS:
        return None

    cleaned = requested_model.strip().lower()
    norm_req = normalize_token(cleaned)

    # 1. Exact match by public_id
    for model in DEFAULT_GEMINI_MODELS:
        if model.public_id == cleaned or normalize_token(model.public_id) == norm_req:
            return model

    # 2. Match by ui_label or alternate_labels
    for model in DEFAULT_GEMINI_MODELS:
        for label in model.ui_labels:
            if normalize_token(label) == norm_req:
                return model

    # 3. Partial / substring match
    if "flashlite" in norm_req or "lite" in norm_req:
        for model in DEFAULT_GEMINI_MODELS:
            if "lite" in model.public_id:
                return model
    if "thinking" in norm_req:
        for model in DEFAULT_GEMINI_MODELS:
            if "thinking" in model.public_id:
                return model
    if "pro" in norm_req:
        for model in DEFAULT_GEMINI_MODELS:
            if model.public_id == "gemini-3.1-pro":
                return model
    if "flash" in norm_req:
        for model in DEFAULT_GEMINI_MODELS:
            if model.public_id == "gemini-3.8-flash":
                return model

    return None
