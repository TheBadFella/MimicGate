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
_DYNAMIC_MODEL_ID = re.compile(r"^(?:gpt-[a-z0-9][a-z0-9._-]*|o\d[a-z0-9._-]*)$")
_DISCOVERED_MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

REASONING_EFFORT_ORDER = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra")
_REASONING_ALIASES: dict[str, tuple[str, ...]] = {
    "none": ("none", "off", "disabled", "no reasoning"),
    "minimal": ("minimal", "minimum", "min", "lowest"),
    "low": ("low", "light", "instant", "fast"),
    "medium": ("medium", "med", "balanced", "normal", "standard", "default", "auto"),
    "high": ("high", "deep", "extended", "thinking", "strong"),
    "xhigh": ("xhigh", "x-high", "extra high", "very high", "extreme"),
    "max": ("max", "maximum", "highest"),
    "ultra": ("ultra", "ultra high", "ultrahigh"),
}


@dataclass(frozen=True)
class BrowserModelOption:
    """A public API model id paired with the ChatGPT UI label to click."""

    public_id: str
    ui_label: str
    alternate_labels: tuple[str, ...] = ()
    setting_label: str = ""

    @property
    def ui_labels(self) -> tuple[str, ...]:
        """All visible labels that may identify this model in ChatGPT's UI."""
        return (self.ui_label, *self.alternate_labels)


@dataclass(frozen=True)
class ResolvedModelRequest:
    """A concrete browser model plus an optional reasoning effort."""

    model: BrowserModelOption | None
    reasoning_effort: str | None = None
    reasoning_from_model_id: bool = False


_discovered_models: dict[str, BrowserModelOption] = {}
_discovered_reasoning: dict[str, tuple[str, ...]] = {}


def normalize_model_token(value: str) -> str:
    """Normalize model ids / labels for resilient matching."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower())


def model_label_to_public_id(label: str) -> str:
    value = re.sub(r"[^a-z0-9.]+", "-", (label or "").strip().lower()).strip("-")
    return re.sub(r"-{2,}", "-", value)


def public_model_id_to_ui_label(model_id: str) -> str:
    value = (model_id or "").strip().lower()
    if value.startswith("gpt-"):
        parts = [part for part in value[4:].split("-") if part]
        return "GPT-" + (parts[0] if parts else "") + (
            " " + " ".join(part.capitalize() for part in parts[1:]) if len(parts) > 1 else ""
        )
    return value


def canonical_reasoning_effort(value: str | None, *, substring: bool = False) -> str | None:
    raw = re.sub(r"[_:.\-]+", " ", (value or "").strip().lower())
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw:
        return None
    compact = normalize_model_token(raw)
    for effort in ("ultra", "xhigh", "max", "none", "minimal", "medium", "high", "low"):
        for alias in _REASONING_ALIASES[effort]:
            alias_compact = normalize_model_token(alias)
            if compact == alias_compact:
                return effort
            if substring and (alias in raw or (alias_compact and alias_compact in compact)):
                return effort
    return None


def reasoning_aliases() -> tuple[str, ...]:
    values = {alias for aliases in _REASONING_ALIASES.values() for alias in aliases}
    values.update(REASONING_EFFORT_ORDER)
    return tuple(sorted(values, key=lambda value: (-len(value), value)))


def choose_reasoning_label(
    requested: str,
    available_labels: list[str] | tuple[str, ...],
) -> tuple[str, str]:
    """Choose the closest available UI reasoning row."""
    labels = [label.strip() for label in available_labels if label and label.strip()]
    if not labels:
        return "", ""
    requested_token = normalize_model_token(requested)
    for label in labels:
        label_token = normalize_model_token(label)
        if requested_token and (requested_token in label_token or label_token in requested_token):
            effort = canonical_reasoning_effort(label, substring=True) or canonical_reasoning_effort(requested)
            return label, effort or model_label_to_public_id(label)
    requested_effort = canonical_reasoning_effort(requested) or "medium"
    requested_rank = REASONING_EFFORT_ORDER.index(requested_effort)
    candidates: list[tuple[int, bool, int, str, str]] = []
    for position, label in enumerate(labels):
        effort = canonical_reasoning_effort(label, substring=True)
        if effort:
            rank = REASONING_EFFORT_ORDER.index(effort)
            candidates.append((abs(rank - requested_rank), rank < requested_rank, position, label, effort))
    if not candidates:
        return labels[0], requested_effort
    _, _, _, label, effort = min(candidates)
    return label, effort


def register_discovered_models(labels: list[str] | tuple[str, ...]) -> list[BrowserModelOption]:
    registered: list[BrowserModelOption] = []
    for label in labels:
        ui_label = (label or "").strip()
        public_id = model_label_to_public_id(ui_label)
        if not ui_label or not _DISCOVERED_MODEL_ID.fullmatch(public_id):
            continue
        option = BrowserModelOption(public_id=public_id, ui_label=ui_label)
        _discovered_models[normalize_model_token(public_id)] = option
        registered.append(option)
    return registered


def register_discovered_reasoning(model: str, labels: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    option = _resolve_base_model(model)
    key = normalize_model_token(option.public_id if option else model)
    cleaned = tuple(dict.fromkeys(label.strip() for label in labels if label and label.strip()))
    if key:
        _discovered_reasoning[key] = cleaned
    return cleaned


def list_reasoning_labels(model: str) -> tuple[str, ...]:
    option = _resolve_base_model(model)
    key = normalize_model_token(option.public_id if option else model)
    return _discovered_reasoning.get(key, ())


def get_discovered_catalog() -> tuple[list[str], dict[str, tuple[str, ...]]]:
    labels = [option.ui_label for option in _discovered_models.values()]
    reasoning = {
        option.public_id: tuple(_discovered_reasoning.get(key, ()))
        for key, option in _discovered_models.items()
    }
    return labels, reasoning


def replace_discovered_catalog(
    labels: list[str] | tuple[str, ...],
    reasoning_by_model: dict[str, list[str] | tuple[str, ...]],
) -> None:
    clear_discovered_models()
    for option in register_discovered_models(labels):
        rows = reasoning_by_model.get(option.ui_label) or reasoning_by_model.get(option.public_id) or ()
        register_discovered_reasoning(option.public_id, rows)


def clear_discovered_models() -> None:
    _discovered_models.clear()
    _discovered_reasoning.clear()


def _parse_model_aliases(raw: str) -> list[BrowserModelOption]:
    """Parse a comma-separated alias list like `gpt-5.5=GPT-5.5,gpt-5.6-sol=GPT-5.6 Sol`."""
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


def _parse_model_settings(raw: str) -> dict[str, str]:
    """Parse effort mappings like `gpt-5.6-sol-high=High,gpt-5.5=Instant`."""
    settings: dict[str, str] = {}
    for chunk in (raw or "").split(","):
        item = chunk.strip()
        if not item or "=" not in item:
            continue
        model_key, setting_label = item.split("=", 1)
        normalized = normalize_model_token(model_key)
        setting_label = setting_label.strip()
        if normalized and setting_label:
            settings[normalized] = setting_label
    return settings


def _apply_model_settings(options: list[BrowserModelOption], raw_settings: str) -> list[BrowserModelOption]:
    """Attach optional picker setting labels to configured model options."""
    settings = _parse_model_settings(raw_settings)
    if not settings:
        return options

    configured: list[BrowserModelOption] = []
    for option in options:
        lookup_keys = [
            normalize_model_token(option.public_id),
            *(normalize_model_token(label) for label in option.ui_labels),
        ]
        setting_label = next((settings[key] for key in lookup_keys if key in settings), "")
        if not setting_label:
            configured.append(option)
            continue
        configured.append(
            BrowserModelOption(
                public_id=option.public_id,
                ui_label=option.ui_label,
                alternate_labels=option.alternate_labels,
                setting_label=setting_label,
            )
        )
    return configured


def list_switchable_models() -> list[BrowserModelOption]:
    """Return configured and live-discovered browser-switchable models."""
    options = _parse_model_aliases(Config.CHATGPT_MODEL_ALIASES)
    seen = {normalize_model_token(option.public_id) for option in options}
    options.extend(option for key, option in _discovered_models.items() if key not in seen)
    return _apply_model_settings(options, Config.CHATGPT_MODEL_SETTINGS)


def _family_aliases(options: list[BrowserModelOption]) -> dict[str, BrowserModelOption]:
    families: dict[str, list[BrowserModelOption]] = {}
    for option in options:
        match = re.match(r"^(gpt-\d+(?:\.\d+)+)-.+$", option.public_id.lower())
        if match:
            families.setdefault(match.group(1), []).append(option)
    return {family: matches[0] for family, matches in families.items() if len(matches) == 1}


def list_public_chat_models() -> list[str]:
    """Return base ids plus live-discovered reasoning variants."""
    options = list_switchable_models()
    aliases = _family_aliases(options)
    model_ids = [PUBLIC_BROWSER_MODEL_ID]
    for option in options:
        model_ids.append(option.public_id)
        model_ids.extend(
            f"{option.public_id}-{effort}"
            for effort in dict.fromkeys(
                canonical_reasoning_effort(label, substring=True) or model_label_to_public_id(label)
                for label in list_reasoning_labels(option.public_id)
            )
            if effort
        )
    for alias, option in aliases.items():
        model_ids.append(alias)
        model_ids.extend(
            f"{alias}-{effort}"
            for effort in dict.fromkeys(
                canonical_reasoning_effort(label, substring=True) or model_label_to_public_id(label)
                for label in list_reasoning_labels(option.public_id)
            )
            if effort
        )
    return list(dict.fromkeys(model_ids))


def _find_known_base_model(model: str) -> BrowserModelOption | None:
    normalized = normalize_model_token(model)
    options = list_switchable_models()
    for option in options:
        labels = {normalize_model_token(label) for label in option.ui_labels}
        if normalized in {normalize_model_token(option.public_id), *labels}:
            return option
    return _family_aliases(options).get((model or "").strip().lower())


def _resolve_base_model(model: str) -> BrowserModelOption | None:
    known = _find_known_base_model(model)
    if known:
        return known
    requested = (model or "").strip().lower()
    if _DYNAMIC_MODEL_ID.fullmatch(requested):
        return BrowserModelOption(requested, public_model_id_to_ui_label(requested))
    return None


def _split_reasoning_suffix(model: str) -> tuple[str, str | None]:
    value = (model or "").strip()
    lowered = value.lower()
    for alias in reasoning_aliases():
        suffix = re.sub(r"[^a-z0-9]+", "-", alias.lower()).strip("-")
        for separator in ("-", ":"):
            marker = separator + suffix
            if lowered.endswith(marker) and len(value) > len(marker):
                return value[: -len(marker)], canonical_reasoning_effort(alias)
    return value, None


def resolve_model_request(
    model: str,
    reasoning_effort: str | None = None,
) -> ResolvedModelRequest:
    """Resolve a base model and reasoning request; a model suffix wins."""
    normalized = normalize_model_token(model)
    if normalized in {normalize_model_token(value) for value in _AUTO_MODEL_IDS}:
        default_model = (Config.CHATGPT_DEFAULT_MODEL or "").strip()
        explicit = canonical_reasoning_effort(reasoning_effort) or (
            (reasoning_effort or "").strip().lower() or None
        )
        if not default_model:
            return ResolvedModelRequest(None, explicit, False)
        model = default_model

    known_direct = _find_known_base_model(model)
    direct = known_direct or _resolve_base_model(model)
    explicit = canonical_reasoning_effort(reasoning_effort) or (
        (reasoning_effort or "").strip().lower() or None
    )
    if known_direct:
        return ResolvedModelRequest(known_direct, explicit, False)
    base, embedded_effort = _split_reasoning_suffix(model)
    if embedded_effort and normalize_model_token(base) != normalize_model_token(model):
        base_option = _resolve_base_model(base)
        if base_option:
            return ResolvedModelRequest(base_option, embedded_effort, True)
    return ResolvedModelRequest(direct, explicit, False)


def is_supported_chat_model(model: str) -> bool:
    """Return whether a request model is supported by the browser gateway."""
    normalized = normalize_model_token(model)
    if normalized in {normalize_model_token(v) for v in _AUTO_MODEL_IDS}:
        return True

    if _resolve_base_model(model):
        return True
    base, effort = _split_reasoning_suffix(model)
    return bool(effort and _resolve_base_model(base))


def resolve_requested_model(model: str) -> BrowserModelOption | None:
    """
    Resolve the requested public model id to a ChatGPT UI label.

    `catgpt-browser` and other auto aliases only trigger a model switch when
    `CHATGPT_DEFAULT_MODEL` is configured to one of the explicit models.
    """
    return resolve_model_request(model).model

