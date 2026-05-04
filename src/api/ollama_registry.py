"""
Ollama compatibility registry and metadata helpers.

Provides a stable read-only model registry, deterministic digests, lightweight
active-model tracking, and a deterministic embedding fallback for clients that
expect Ollama endpoints.
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass

from src.chatgpt.model_registry import list_public_chat_models, normalize_model_token
from src.config import Config

_STATIC_CREATED_AT = "2026-05-04T00:00:00Z"
_active_models: dict[str, float] = {}


@dataclass(frozen=True)
class OllamaModelProfile:
    """Static profile used by the Ollama compatibility endpoints."""

    name: str
    capability: str
    display_family: str
    parameter_size: str
    quantization_level: str
    size: int
    digest: str


def list_ollama_profiles() -> list[OllamaModelProfile]:
    """Return all configured Ollama-visible profiles."""
    profiles: list[OllamaModelProfile] = []
    seen: set[str] = set()

    for model in list_public_chat_models():
        normalized = normalize_model_token(model)
        if normalized in seen:
            continue
        profiles.append(_build_profile(model, capability="chat"))
        seen.add(normalized)

    for model in _parse_embedding_models(Config.OLLAMA_EMBEDDING_MODELS):
        normalized = normalize_model_token(model)
        if normalized in seen:
            continue
        profiles.append(_build_profile(model, capability="embedding"))
        seen.add(normalized)

    return profiles


def get_ollama_profile(name: str) -> OllamaModelProfile | None:
    """Resolve a profile by model name, case-insensitively."""
    target = normalize_model_token(name)
    for profile in list_ollama_profiles():
        if normalize_model_token(profile.name) == target:
            return profile
    return None


def list_tags_payload() -> dict:
    """Payload for GET /api/tags."""
    return {
        "models": [build_tag_entry(profile) for profile in list_ollama_profiles()],
    }


def build_tag_entry(profile: OllamaModelProfile) -> dict:
    """Single tag entry in Ollama's model list shape."""
    return {
        "name": profile.name,
        "model": profile.name,
        "modified_at": _STATIC_CREATED_AT,
        "size": profile.size,
        "digest": profile.digest,
        "details": _details_dict(profile),
    }


def build_show_payload(profile: OllamaModelProfile) -> dict:
    """Static metadata for POST /api/show."""
    return {
        "license": "Proprietary browser-backed compatibility profile.",
        "modelfile": _build_modelfile(profile),
        "parameters": _build_parameters(profile),
        "template": "{{ .Prompt }}",
        "system": "",
        "details": _details_dict(profile),
        "model_info": {
            "general.architecture": "catgpt-browser",
            "general.parameter_count": profile.parameter_size,
            "general.quantization_version": profile.quantization_level,
            "general.capability": profile.capability,
            "general.embedding_dimensions": (
                Config.OLLAMA_EMBEDDING_DIMENSIONS if profile.capability == "embedding" else 0
            ),
        },
        "capabilities": [profile.capability],
        "modified_at": _STATIC_CREATED_AT,
        "digest": profile.digest,
    }


def mark_model_active(name: str) -> None:
    """Mark a model as recently used for /api/ps."""
    profile = get_ollama_profile(name)
    if profile is None:
        return
    _active_models[profile.name] = time.time()


def list_active_models_payload() -> dict:
    """Payload for POST /api/ps."""
    now = time.time()
    ttl = max(1, Config.OLLAMA_ACTIVE_MODEL_TTL_SECONDS)
    expired = [name for name, ts in _active_models.items() if now - ts > ttl]
    for name in expired:
        _active_models.pop(name, None)

    models = []
    for name, last_used in sorted(_active_models.items(), key=lambda item: item[1], reverse=True):
        profile = get_ollama_profile(name)
        if profile is None:
            continue
        models.append({
            "name": profile.name,
            "model": profile.name,
            "size": profile.size,
            "digest": profile.digest,
            "details": _details_dict(profile),
            "expires_at": _iso_ts(last_used + ttl),
            "size_vram": max(0, profile.size // 2),
        })

    return {"models": models}


def build_pull_status_payload(name: str) -> dict:
    """Success payload for POST /api/pull when the model exists in the registry."""
    profile = get_ollama_profile(name)
    if profile is None:
        raise KeyError(name)
    mark_model_active(profile.name)
    return {
        "status": "success",
        "digest": profile.digest,
        "total": profile.size,
        "completed": profile.size,
    }


def build_delete_status_payload(name: str) -> dict:
    """Success payload for DELETE /api/delete safety mock."""
    return {
        "status": "success",
        "deleted": name,
        "mocked": True,
    }


def build_copy_unsupported_payload(source: str, destination: str) -> dict:
    """Unsupported payload for POST /api/copy."""
    return {
        "error": f"Copy is not supported for browser-backed model '{source}' -> '{destination}'.",
    }


def generate_embeddings(name: str, inputs: list[str]) -> dict:
    """
    Deterministic embedding fallback for Ollama-compatible clients.

    This is a compatibility shim, not a semantic embedding model.
    """
    profile = get_ollama_profile(name)
    if profile is None:
        raise KeyError(name)

    mark_model_active(profile.name)
    vectors = [_embedding_vector(profile.name, text, Config.OLLAMA_EMBEDDING_DIMENSIONS) for text in inputs]
    return {
        "model": profile.name,
        "embeddings": vectors,
        "total_duration": 0,
        "load_duration": 0,
        "prompt_eval_count": sum(len(text) for text in inputs),
    }


def _parse_embedding_models(raw: str) -> list[str]:
    values: list[str] = []
    for chunk in (raw or "").split(","):
        item = chunk.strip()
        if item:
            values.append(item)
    return values


def _build_profile(name: str, capability: str) -> OllamaModelProfile:
    digest = _digest_for_model(name)
    size = _stable_size_bytes(name, capability)
    parameter_size = "browser-managed" if capability == "chat" else f"{Config.OLLAMA_EMBEDDING_DIMENSIONS}d"
    quantization = "compat" if capability == "chat" else "compat-embed"
    family = "catgpt-browser" if capability == "chat" else "catgpt-embed"
    return OllamaModelProfile(
        name=name,
        capability=capability,
        display_family=family,
        parameter_size=parameter_size,
        quantization_level=quantization,
        size=size,
        digest=digest,
    )


def _digest_for_model(name: str) -> str:
    return f"sha256:{hashlib.sha256(f'ollama:{name}'.encode('utf-8')).hexdigest()}"


def _stable_size_bytes(name: str, capability: str) -> int:
    digest = hashlib.sha256(f"size:{capability}:{name}".encode("utf-8")).digest()
    seed = int.from_bytes(digest[:4], "big")
    if capability == "embedding":
        base = 256 * 1024 * 1024
        span = 768 * 1024 * 1024
    else:
        base = 2 * 1024 * 1024 * 1024
        span = 6 * 1024 * 1024 * 1024
    return base + (seed % span)


def _build_modelfile(profile: OllamaModelProfile) -> str:
    return (
        f"FROM {profile.name}\n"
        f"# capability: {profile.capability}\n"
        "# backend: ChatGPT browser automation compatibility layer\n"
    )


def _build_parameters(profile: OllamaModelProfile) -> str:
    if profile.capability == "embedding":
        return f"embedding_dimensions {Config.OLLAMA_EMBEDDING_DIMENSIONS}\ntruncate false"
    return "num_ctx 32768\nnum_predict 4096"


def _details_dict(profile: OllamaModelProfile) -> dict:
    return {
        "parent_model": "",
        "format": "compat",
        "family": profile.display_family,
        "families": [profile.display_family],
        "parameter_size": profile.parameter_size,
        "quantization_level": profile.quantization_level,
    }


def _embedding_vector(model_name: str, text: str, dimensions: int) -> list[float]:
    dims = max(8, dimensions)
    values: list[float] = []
    counter = 0

    while len(values) < dims:
        payload = f"{model_name}\n{counter}\n{text}".encode("utf-8")
        digest = hashlib.sha256(payload).digest()
        for index in range(0, len(digest), 2):
            if len(values) >= dims:
                break
            raw = int.from_bytes(digest[index:index + 2], "big") / 65535.0
            values.append((raw * 2.0) - 1.0)
        counter += 1

    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [round(v / norm, 8) for v in values]


def _iso_ts(value: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))

