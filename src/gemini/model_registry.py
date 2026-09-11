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

REASONING_EFFORT_ORDER = ("none", "minimal", "low", "medium", "high", "xhigh", "extended", "max", "ultra")

_REASONING_ALIASES = {
    "off": "none",
    "disabled": "none",
    "min": "minimal",
    "med": "medium",
    "standard": "medium",
    "deep": "extended",
    "thinking": "extended",
    "complex": "extended",
}

_discovered_models: list[GeminiModelOption] = []


def canonical_reasoning_effort(value: str | None, *, substring: bool = False) -> str | None:
    """Normalize user-facing reasoning effort tokens to canonical names."""
    if not value:
        return None
    raw = value.strip().lower()
    if raw in _REASONING_ALIASES:
        return _REASONING_ALIASES[raw]
    if raw in REASONING_EFFORT_ORDER:
        return raw
    if substring:
        for name in REASONING_EFFORT_ORDER:
            if name in raw:
                return name
        for alias, target in _REASONING_ALIASES.items():
            if alias in raw:
                return target
    return None


def register_discovered_gemini_models(labels: list[str]) -> list[str]:
    """Register dynamically discovered models from the active Gemini browser UI."""
    global _discovered_models
    added_ids: list[str] = []
    known_labels = {normalize_token(m.ui_label) for m in DEFAULT_GEMINI_MODELS + tuple(_discovered_models)}

    for label in labels:
        first_line = label.splitlines()[0].strip() if label else ""
        if not first_line:
            continue
        norm = normalize_token(first_line)
        if not norm or norm in known_labels:
            continue

        slug = re.sub(r"[^a-z0-9.]+", "-", first_line.lower()).strip("-")
        public_id = f"gemini-{slug}" if not slug.startswith("gemini-") else slug
        opt = GeminiModelOption(
            public_id=public_id,
            ui_label=first_line,
            alternate_labels=(first_line, label.strip()),
        )
        _discovered_models.append(opt)
        known_labels.add(norm)
        added_ids.append(public_id)

    return added_ids


def normalize_token(value: str) -> str:
    """Normalize model tokens for resilient comparison."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower())


def list_gemini_model_ids() -> tuple[str, ...]:
    """Return all public model IDs supported by the Gemini provider."""
    all_models = DEFAULT_GEMINI_MODELS + tuple(_discovered_models)
    seen: set[str] = set()
    unique_ids: list[str] = [PUBLIC_GEMINI_BROWSER_MODEL_ID]
    for m in all_models:
        if m.public_id not in seen:
            seen.add(m.public_id)
            unique_ids.append(m.public_id)
    return tuple(unique_ids)


def resolve_gemini_model(
    requested_model: str | None,
    reasoning_effort: str | None = None,
) -> GeminiModelOption | None:
    """
    Resolve a requested model ID and optional reasoning effort to a GeminiModelOption.
    Returns None if the requested model means 'use whatever is currently selected in browser'.
    """
    effort = canonical_reasoning_effort(reasoning_effort)
    thinking_model = GeminiModelOption(
        public_id="gemini-extended-thinking",
        ui_label="Extended thinking",
        alternate_labels=("Thinking", "Complex problem solving"),
    )

    # 1. Explicit reasoning effort takes precedence
    if effort in {"high", "xhigh", "extended", "max", "ultra"}:
        return thinking_model

    cleaned = (requested_model or "").strip().lower()
    norm_req = normalize_token(cleaned)

    # 2. Check auto model
    if is_auto_model(requested_model):
        if effort in {"none", "minimal", "low"}:
            # Ensure non-thinking Flash is used if auto was requested with low reasoning
            return GeminiModelOption(
                public_id="gemini-3.8-flash",
                ui_label="3.8 Flash",
                alternate_labels=("Flash", "3.6 Flash", "Fastest answers"),
            )
        return None

    # If low/none reasoning effort requested with a thinking model, downgrade to Pro or Flash
    if effort in {"none", "minimal", "low"}:
        if "pro" in norm_req:
            return GeminiModelOption(
                public_id="gemini-3.1-pro",
                ui_label="3.1 Pro",
                alternate_labels=("Pro", "Advanced reasoning"),
            )
        return GeminiModelOption(
            public_id="gemini-3.8-flash",
            ui_label="3.8 Flash",
            alternate_labels=("Flash", "3.6 Flash", "Fastest answers"),
        )

    all_models = DEFAULT_GEMINI_MODELS + tuple(_discovered_models)

    # 3. Exact match by public_id
    for model in all_models:
        if model.public_id == cleaned or normalize_token(model.public_id) == norm_req:
            return model

    # 4. Match by ui_label or alternate_labels
    for model in all_models:
        for label in model.ui_labels:
            if normalize_token(label) == norm_req:
                return model

    # 5. Partial / substring match
    if "flashlite" in norm_req or "lite" in norm_req:
        for model in all_models:
            if "lite" in model.public_id:
                return model
    if "thinking" in norm_req:
        return thinking_model
    if "pro" in norm_req:
        for model in all_models:
            if model.public_id == "gemini-3.1-pro":
                return model
    if "flash" in norm_req:
        for model in all_models:
            if model.public_id == "gemini-3.8-flash":
                return model

    return None
