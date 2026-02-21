"""
OpenAI-compatible API routes.

Provides:
  POST /v1/chat/completions   - chat completions (with tool/function calling)
  GET  /v1/models             - list available models

All requests are serialized through an asyncio.Lock because the underlying
Playwright browser page is single-threaded.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from src.api.openai_schemas import (
    ChatCompletionAsyncRequest,
    ChatCompletionJobResponse,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Choice,
    ChoiceMessage,
    FunctionCallInfo,
    ImageData,
    ImageGenerationRequest,
    ImagesResponse,
    ModelListResponse,
    ModelObject,
    ToolCall,
    ToolDefinition,
    UsageInfo,
)
from src.chatgpt.client import ChatGPTClient
from src.config import Config
from src.log import setup_logging

log = setup_logging("openai_routes")

openai_router = APIRouter()

# Global reference - set by server.py at startup
_client: ChatGPTClient | None = None

# Serialize all requests - single browser page, not thread-safe
_lock = asyncio.Lock()
_jobs_lock = asyncio.Lock()
_jobs: dict[str, ChatCompletionJobResponse] = {}
_cache_lock = asyncio.Lock()
_response_cache: dict[str, tuple[float, ChatCompletionResponse]] = {}
_contract_lock = asyncio.Lock()
_thread_contracts: dict[str, tuple[float, str]] = {}
_app_thread_lock = asyncio.Lock()
_app_threads: dict[str, tuple[float, str]] = {}

MODEL_ID = "catgpt-browser"
_CACHE_TTL_SECONDS = 600
_CACHE_MAX_ENTRIES = 256
_CONTRACT_TTL_SECONDS = max(60, Config.API_THREAD_CONTRACT_TTL_SECONDS)
_APP_THREAD_TTL_SECONDS = max(300, Config.API_APP_THREAD_TTL_SECONDS)


def set_openai_client(client: ChatGPTClient) -> None:
    """Called by server.py to inject the ChatGPT client."""
    global _client
    _client = client


def _get_client() -> ChatGPTClient:
    if _client is None:
        raise HTTPException(status_code=503, detail="ChatGPT client not initialized")
    return _client


# -- Helpers -----------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars per token)."""
    return max(1, len(text) // 4)


def _shrink_for_cache(value: Any) -> Any:
    """Reduce large strings to a digest so cache-key generation stays cheap."""
    if isinstance(value, str):
        if len(value) > 512:
            digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
            return f"sha256:{digest}:len:{len(value)}"
        return value
    if isinstance(value, list):
        return [_shrink_for_cache(v) for v in value]
    if isinstance(value, dict):
        return {k: _shrink_for_cache(v) for k, v in value.items()}
    return value


def _cache_key_for_request(request: ChatCompletionRequest) -> str:
    """
    Build a stable cache key for semantic request identity.

    `stream` and `user` are excluded because they do not change prompt content.
    """
    payload = request.model_dump(mode="json", exclude={"stream", "user"})
    compact_payload = _shrink_for_cache(payload)
    canonical = json.dumps(compact_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _clone_cached_response(cached: ChatCompletionResponse) -> ChatCompletionResponse:
    """Return a fresh response object so ids/timestamps remain request-specific."""
    return cached.model_copy(
        deep=True,
        update={
            "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
            "created": int(time.time()),
        },
    )


def _prune_cache(now: float) -> None:
    """Prune expired entries and enforce size cap."""
    expired_keys = [key for key, (ts, _) in _response_cache.items() if now - ts > _CACHE_TTL_SECONDS]
    for key in expired_keys:
        _response_cache.pop(key, None)

    if len(_response_cache) <= _CACHE_MAX_ENTRIES:
        return

    ordered = sorted(_response_cache.items(), key=lambda item: item[1][0])
    overflow = len(_response_cache) - _CACHE_MAX_ENTRIES
    for key, _ in ordered[:overflow]:
        _response_cache.pop(key, None)


def _contract_hash(system_texts: list[str]) -> str:
    """Stable hash for thread-level system instruction contracts."""
    canonical = json.dumps(
        [_normalize_instruction_text(t) for t in system_texts if t.strip()],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _prune_thread_contracts(now: float) -> None:
    """Drop expired thread contract mappings."""
    expired = [tid for tid, (ts, _) in _thread_contracts.items() if now - ts > _CONTRACT_TTL_SECONDS]
    for tid in expired:
        _thread_contracts.pop(tid, None)


def _prune_app_threads(now: float) -> None:
    """Drop expired app->thread mappings."""
    expired = [app for app, (ts, _) in _app_threads.items() if now - ts > _APP_THREAD_TTL_SECONDS]
    for app in expired:
        _app_threads.pop(app, None)


def _build_contract_reminder_prompt(user_text: str, contract_id: str) -> str:
    """Compact prompt that reuses previously primed thread instructions."""
    short_id = contract_id[:12]
    return (
        f"[Contract {short_id}] Reuse the established instructions for this thread exactly.\n\n"
        f"{user_text}"
    )


def _extract_content_text(content) -> str:
    """Extract text from message content (handles both string and list format)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(parts) if parts else ""
    return str(content)


def _normalize_instruction_text(text: str) -> str:
    """Normalize instruction text for duplicate/equivalence checks."""
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _collect_system_texts(messages: list[ChatMessage]) -> list[str]:
    """Collect non-empty system message texts."""
    texts: list[str] = []
    for msg in messages:
        if msg.role != "system":
            continue
        text = _extract_content_text(msg.content).strip()
        if text:
            texts.append(text)
    return texts


def _dedupe_system_messages(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Remove duplicate system messages while preserving order."""
    deduped: list[ChatMessage] = []
    seen: set[str] = set()

    for msg in messages:
        if msg.role != "system":
            deduped.append(msg)
            continue

        text = _extract_content_text(msg.content).strip()
        key = _normalize_instruction_text(text)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        deduped.append(msg)

    return deduped


def _looks_like_json_only_instruction(text: str) -> bool:
    """Heuristic detection for a generic JSON-only system instruction."""
    normalized = _normalize_instruction_text(text)
    return (
        "valid json only" in normalized
        and "markdown/code fences" in normalized
    )


def _has_equivalent_response_instruction(
    messages: list[ChatMessage], response_format_system: str
) -> bool:
    """Check if an equivalent structured-output instruction already exists."""
    target = _normalize_instruction_text(response_format_system)
    if not target:
        return False

    for text in _collect_system_texts(messages):
        normalized = _normalize_instruction_text(text)
        if normalized == target:
            return True

    # Generic json_object instruction can be considered equivalent even if phrasing differs.
    if "return exactly one json object" in target:
        return any(_looks_like_json_only_instruction(text) for text in _collect_system_texts(messages))

    return False


def _extract_image_urls(content) -> list[str]:
    """Extract image URLs from message content (OpenAI vision format)."""
    if not isinstance(content, list):
        return []
    urls = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "image_url":
            image_url = item.get("image_url", {})
            if isinstance(image_url, dict):
                url = image_url.get("url", "")
            else:
                url = str(image_url)
            if url:
                urls.append(url)
    return urls


def _extract_file_attachments(content) -> list[dict]:
    """
    Extract file attachments from message content.

    Supported content part format:
      {"type": "file", "file": {"filename": "test.pdf", "data": "base64...", "mime_type": "application/pdf"}}

    Also supports a shorthand data-URL style:
      {"type": "file", "file": {"filename": "test.pdf", "url": "data:application/pdf;base64,..."}}

    Returns list of dicts: [{"filename": str, "data_b64": str, "mime_type": str}, ...]
    """
    if not isinstance(content, list):
        return []
    files = []
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "file":
            continue
        file_info = item.get("file", {})
        if not isinstance(file_info, dict):
            continue
        filename = file_info.get("filename", "attachment")
        # Two ways to supply file data:
        # 1. data + mime_type  2. url (data-URL)
        data_b64 = file_info.get("data")
        mime_type = file_info.get("mime_type", "application/octet-stream")
        url = file_info.get("url", "")
        if not data_b64 and url.startswith("data:"):
            # Parse data URL
            try:
                header, data_b64 = url.split(",", 1)
                # header = "data:application/pdf;base64"
                if ":" in header and ";" in header:
                    mime_type = header.split(":")[1].split(";")[0]
            except ValueError:
                continue
        if data_b64:
            files.append({"filename": filename, "data_b64": data_b64, "mime_type": mime_type})
    return files


async def _download_file(url_or_data: str | dict, download_dir: str = "/tmp/catgpt_files") -> str | None:
    """
    Download / decode a file (image, PDF, etc.) from URL, base64 data URL,
    or a file attachment dict. Returns the local file path.
    """
    import base64
    import hashlib
    import os

    os.makedirs(download_dir, exist_ok=True)

    # -- Dict form (from _extract_file_attachments) --
    if isinstance(url_or_data, dict):
        try:
            filename = url_or_data.get("filename", "file")
            data_b64 = url_or_data["data_b64"]
            # Sanitize filename
            safe_name = re.sub(r"[^\w.\-]", "_", filename)
            hash_suffix = hashlib.md5(data_b64[:60].encode()).hexdigest()[:8]
            filepath = os.path.join(download_dir, f"{hash_suffix}_{safe_name}")
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(data_b64))
            log.info(f"Decoded file attachment: {filepath}")
            return filepath
        except Exception as e:
            log.error(f"Failed to decode file attachment: {e}")
            return None

    # -- String forms --
    url = str(url_or_data)

    if url.startswith("data:"):
        # Base64 data URL: data:image/png;base64,iVBOR... or data:application/pdf;base64,...
        try:
            header, b64data = url.split(",", 1)
            # Detect extension from MIME type
            ext = "bin"
            mime = ""
            if ":" in header and ";" in header:
                mime = header.split(":")[1].split(";")[0]
            ext_map = {
                "image/png": "png", "image/jpeg": "jpg", "image/webp": "webp",
                "image/gif": "gif", "application/pdf": "pdf",
                "text/plain": "txt", "text/csv": "csv",
                "application/json": "json",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
            }
            ext = ext_map.get(mime, mime.split("/")[-1] if "/" in mime else "bin")
            filename = f"file_{hashlib.md5(b64data[:100].encode()).hexdigest()[:12]}.{ext}"
            filepath = os.path.join(download_dir, filename)
            with open(filepath, "wb") as f:
                f.write(base64.b64decode(b64data))
            log.info(f"Decoded base64 file: {filepath}")
            return filepath
        except Exception as e:
            log.error(f"Failed to decode base64 data URL: {e}")
            return None
    elif url.startswith(("http://", "https://")):
        # HTTP URL - download it
        try:
            import urllib.request
            ext = "bin"
            for e in ["jpg", "jpeg", "webp", "gif", "png", "pdf", "txt", "csv", "docx", "xlsx"]:
                if e in url.lower():
                    ext = e
                    break
            filename = f"file_{hashlib.md5(url.encode()).hexdigest()[:12]}.{ext}"
            filepath = os.path.join(download_dir, filename)
            urllib.request.urlretrieve(url, filepath)
            log.info(f"Downloaded file: {filepath}")
            return filepath
        except Exception as e:
            log.error(f"Failed to download file from {url}: {e}")
            return None
    elif os.path.isfile(url):
        # Local file path
        return url
    else:
        log.warning(f"Unknown file URL format: {url[:80]}")
        return None


def _build_prompt(messages: list[ChatMessage]) -> str:
    """
    Flatten an OpenAI-style message array into a single prompt string
    that we can paste into ChatGPT's input box.

    The browser already maintains conversation context within a thread,
    so for simple single-turn calls we just send the last user message.
    For multi-turn with system prompts or tool results, we build a
    formatted transcript.
    """
    # Simple case: only one user message (and optionally one system message)
    non_system = [m for m in messages if m.role != "system"]
    system_msgs = [m for m in messages if m.role == "system"]

    # If it's just one user message, send it directly
    if len(non_system) == 1 and non_system[0].role == "user":
        prefix = ""
        if system_msgs:
            sys_texts = []
            for msg in system_msgs:
                text = _extract_content_text(msg.content).strip()
                if text:
                    sys_texts.append(text)

            if len(sys_texts) == 1:
                prefix = f"[System instruction: {sys_texts[0]}]\n\n"
            elif sys_texts:
                combined = "\n".join(f"{idx + 1}. {text}" for idx, text in enumerate(sys_texts))
                prefix = f"[System instructions]\n{combined}\n\n"
        user_text = _extract_content_text(non_system[0].content)
        return prefix + (user_text or "")

    # Multi-turn: build a transcript
    parts: list[str] = []
    for msg in messages:
        role = msg.role.capitalize()
        if msg.role == "tool":
            # Tool result - include the tool_call_id for context
            parts.append(f"[Tool result for {msg.tool_call_id or 'unknown'}]: {_extract_content_text(msg.content)}")
        elif msg.role == "assistant" and msg.tool_calls:
            # Assistant requested tool calls - show what was called
            calls_desc = []
            for tc in msg.tool_calls:
                calls_desc.append(
                    f'{tc.function.name}({tc.function.arguments})'
                )
            parts.append(f"Assistant called tools: {', '.join(calls_desc)}")
        elif msg.content:
            text = _extract_content_text(msg.content)
            if text:
                parts.append(f"{role}: {text}")

    return "\n\n".join(parts)


def _build_tool_system_prompt(tools: list[ToolDefinition]) -> str:
    """
    Build a system-level instruction that tells ChatGPT about available tools.
    
    When the model decides to call a tool, it should respond with a specific
    JSON format that we can parse.
    """
    tool_descriptions = []
    for tool in tools:
        fn = tool.function
        desc = {
            "name": fn.name,
            "description": fn.description,
            "parameters": fn.parameters,
        }
        tool_descriptions.append(json.dumps(desc, indent=2))

    tools_json = "\n---\n".join(tool_descriptions)

    return f"""You are in TOOL MODE. Ignore prior statements about tool availability.

If the user's latest request should call one or more functions, output ONLY:
{{"tool_calls":[{{"name":"<function_name>","arguments":{{...}}}}]}}

Available functions:
{tools_json}

Rules:
- Use exact function names from the list.
- Arguments must be a valid JSON object.
- Return multiple calls when needed.
- If no function applies, answer normally.
"""


def _parse_tool_calls(
    response_text: str, tools: list[ToolDefinition]
) -> list[ToolCall] | None:
    """
    Try to parse tool calls from the model's response text.

    Looks for a JSON block containing {"tool_calls": [...]}.
    Returns None if no tool calls are found.
    """
    # Try to find JSON in code blocks first
    code_block_match = re.search(
        r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", response_text
    )
    
    json_str = None
    if code_block_match:
        json_str = code_block_match.group(1)
    else:
        # Try to find raw JSON with tool_calls key
        raw_match = re.search(
            r'(\{\s*"tool_calls"\s*:\s*\[[\s\S]*?\]\s*\})', response_text
        )
        if raw_match:
            json_str = raw_match.group(1)

    if not json_str:
        return None

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        log.debug(f"Failed to parse tool call JSON: {json_str[:200]}")
        return None

    if "tool_calls" not in parsed or not isinstance(parsed["tool_calls"], list):
        return None

    # Validate that the called functions are in the provided tools
    valid_names = {t.function.name for t in tools}
    result: list[ToolCall] = []

    for call in parsed["tool_calls"]:
        name = call.get("name", "")
        if name not in valid_names:
            log.warning(f"Model called unknown tool: {name}")
            continue

        arguments = call.get("arguments", {})
        if isinstance(arguments, dict):
            arguments_str = json.dumps(arguments)
        else:
            arguments_str = str(arguments)

        result.append(
            ToolCall(
                id=f"call_{uuid.uuid4().hex[:24]}",
                type="function",
                function=FunctionCallInfo(name=name, arguments=arguments_str),
            )
        )

    return result if result else None


def _build_response_format_system_prompt(response_format: Any) -> str | None:
    """Build a strict JSON-output instruction from OpenAI response_format."""
    if not response_format:
        return None

    if isinstance(response_format, str):
        if response_format == "json_object":
            return (
                "You must respond with valid JSON only. "
                "Return exactly one JSON object and no markdown/code fences."
            )
        return None

    if not isinstance(response_format, dict):
        return None

    rf_type = response_format.get("type")
    if rf_type == "json_object":
        return (
            "You must respond with valid JSON only. "
            "Return exactly one JSON object and no markdown/code fences."
        )

    if rf_type == "json_schema":
        schema_obj = response_format.get("json_schema", {})
        schema = schema_obj.get("schema") if isinstance(schema_obj, dict) else None
        strict = bool(schema_obj.get("strict")) if isinstance(schema_obj, dict) else False
        if schema:
            strict_text = " Follow it strictly." if strict else ""
            return (
                "You must respond with valid JSON only (no markdown/code fences). "
                "The JSON must satisfy this schema:" +
                f"\n{json.dumps(schema, ensure_ascii=False)}" +
                strict_text
            )
        return (
            "You must respond with valid JSON only. "
            "Return exactly one JSON object and no markdown/code fences."
        )

    return None


def _extract_json_payload(text: str) -> Any | None:
    """Extract and parse a JSON object/array from model text."""
    if not text:
        return None

    stripped = text.strip()

    try:
        return json.loads(stripped)
    except Exception:
        pass

    block = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", stripped)
    if block:
        candidate = block.group(1).strip()
        try:
            return json.loads(candidate)
        except Exception:
            pass

    first_obj = stripped.find("{")
    first_arr = stripped.find("[")
    candidates = [i for i in (first_obj, first_arr) if i >= 0]
    if not candidates:
        return None

    start = min(candidates)
    try:
        return json.loads(stripped[start:])
    except Exception:
        return None


def _coerce_payload_to_schema(payload: Any, schema: dict[str, Any]) -> Any:
    """Best-effort payload coercion guided by a JSON schema."""
    schema_type = schema.get("type")

    if schema_type == "object":
        if isinstance(payload, dict):
            return payload

        properties = schema.get("properties", {})
        if not isinstance(properties, dict) or not properties:
            return payload

        if isinstance(payload, list):
            array_keys = [
                key for key, prop in properties.items()
                if isinstance(prop, dict) and prop.get("type") == "array"
            ]
            if len(array_keys) == 1:
                return {array_keys[0]: payload}

            if len(properties) == 1:
                key = next(iter(properties))
                return {key: payload}

            required = schema.get("required", [])
            if isinstance(required, list):
                for key in required:
                    if key in properties:
                        return {key: payload}

        if len(properties) == 1:
            key = next(iter(properties))
            return {key: payload}

        return payload

    if schema_type == "array":
        if isinstance(payload, list):
            return payload

        if isinstance(payload, dict) and len(payload) == 1:
            only_value = next(iter(payload.values()))
            if isinstance(only_value, list):
                return only_value

        return [payload]

    return payload


def _coerce_to_response_schema(payload: Any, response_format: Any) -> Any:
    """Coerce common payload mismatches into the requested response format."""
    if not isinstance(response_format, dict):
        return payload

    rf_type = response_format.get("type")
    if rf_type == "json_object":
        if isinstance(payload, dict):
            return payload
        return {"data": payload}

    if rf_type != "json_schema":
        return payload

    json_schema = response_format.get("json_schema", {})
    if not isinstance(json_schema, dict):
        return payload

    schema = json_schema.get("schema")
    if not isinstance(schema, dict):
        return payload

    return _coerce_payload_to_schema(payload, schema)


def _is_effectively_empty_value(value: Any) -> bool:
    """Return True when a value is effectively empty for header-row detection."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _pick_note_field_name(item: dict[str, Any]) -> str | None:
    """Pick the best note/context field key in an item dict."""
    preferred = ("note", "notes", "context", "header", "section", "group")
    for key in preferred:
        if key in item:
            return key
    return None


def _header_text_from_row(item: Any) -> str | None:
    """
    Detect a header-only row, e.g. {"food": null, "quantity": null, "note": "TO SERVE"}.
    Returns header text if matched, else None.
    """
    if not isinstance(item, dict) or not item:
        return None

    note_key = _pick_note_field_name(item)
    if not note_key:
        return None

    note_val = item.get(note_key)
    if not isinstance(note_val, str) or not note_val.strip():
        return None

    for key, value in item.items():
        if key == note_key:
            continue
        if not _is_effectively_empty_value(value):
            return None

    return note_val.strip()


def _append_note(item: dict[str, Any], text: str) -> None:
    """Append note/context text to an item."""
    key = _pick_note_field_name(item) or "note"
    existing = item.get(key)
    if isinstance(existing, str) and existing.strip():
        item[key] = f"{text}; {existing.strip()}"
    else:
        item[key] = text


def _merge_header_rows_in_array(items: list[Any]) -> list[Any]:
    """Merge header-only rows into the next real row in an array."""
    merged: list[Any] = []
    pending_header: str | None = None

    for raw in items:
        header_text = _header_text_from_row(raw)
        if header_text:
            pending_header = f"{pending_header}; {header_text}" if pending_header else header_text
            continue

        if isinstance(raw, dict) and pending_header:
            item = dict(raw)
            _append_note(item, pending_header)
            merged.append(item)
            pending_header = None
            continue

        merged.append(raw)

    if pending_header:
        # No real row after header; preserve as standalone note row.
        merged.append({"note": pending_header})

    return merged


def _merge_header_rows(payload: Any) -> Any:
    """
    Merge header-only rows into next row for structured payloads.

    Supports:
    - root array of objects
    - root object with exactly one array field
    """
    if isinstance(payload, list):
        return _merge_header_rows_in_array(payload)

    if isinstance(payload, dict):
        array_keys = [k for k, v in payload.items() if isinstance(v, list)]
        if len(array_keys) == 1:
            key = array_keys[0]
            out = dict(payload)
            out[key] = _merge_header_rows_in_array(out[key])
            return out

    return payload


def _normalize_structured_content(response_text: str, response_format: Any) -> str:
    """Best-effort normalization to JSON string for structured output calls."""
    payload = _extract_json_payload(response_text)
    if payload is None:
        return response_text

    payload = _coerce_to_response_schema(payload, response_format)
    if Config.API_HEADER_ROW_MERGE_MODE:
        payload = _merge_header_rows(payload)
    return json.dumps(payload, ensure_ascii=False)


def _latest_user_text(messages: list[ChatMessage]) -> str:
    """Return the latest user text content from request messages."""
    for msg in reversed(messages):
        if msg.role == "user":
            return _extract_content_text(msg.content).strip()
    return ""


def _infer_expected_item_count(messages: list[ChatMessage]) -> int | None:
    """
    Infer expected item count from the latest user text.

    Used as a best-effort guard for structured extraction tasks where output
    cardinality should match input rows.

    Strategy:
    1) If user content is JSON, infer from its primary array cardinality.
    2) Otherwise, fallback to counting non-empty text lines.
    """
    text = _latest_user_text(messages)
    if not text:
        return None

    # Preferred: JSON payloads (e.g., [...], {"items":[...]}, {"ingredients":[...]}).
    payload = _extract_json_payload(text)
    if payload is not None:
        json_count = _infer_primary_array_count(payload)
        if json_count is not None and json_count >= 1:
            return json_count

    # Fallback: line-oriented plain text payloads.
    count = 0
    for line in text.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if cleaned:
            count += 1

    return count if count >= 2 else None


def _infer_primary_array_count(payload: Any) -> int | None:
    """Infer the cardinality of the primary array in a structured payload."""
    if isinstance(payload, list):
        return len(payload)

    if isinstance(payload, dict):
        array_values = [v for v in payload.values() if isinstance(v, list)]
        if len(array_values) == 1:
            return len(array_values[0])

    return None


def _structured_cardinality_mismatch(
    messages: list[ChatMessage], response_text: str
) -> tuple[int, int] | None:
    """Return (expected, actual) if a clear structured cardinality mismatch exists."""
    expected = _infer_expected_item_count(messages)
    if expected is None:
        return None

    payload = _extract_json_payload(response_text)
    if payload is None:
        return None

    actual = _infer_primary_array_count(payload)
    if actual is None:
        return None

    if expected != actual:
        return expected, actual
    return None


def _build_cardinality_retry_prompt(base_prompt: str, expected: int, actual: int) -> str:
    """Build a corrective retry prompt for structured cardinality mismatch."""
    return (
        f"{base_prompt}\n\n"
        "Correction: The previous JSON had the wrong number of items.\n"
        f"Input line count is {expected}, but output count was {actual}.\n"
        "Return valid JSON only, with exactly one output item per non-empty input line, "
        "preserving input order. Do not merge or drop lines."
    )


# -- Routes ------------------------------------------------------


@openai_router.get("/v1/models", response_model=ModelListResponse)
async def list_models() -> ModelListResponse:
    """List available models - returns our single browser-backed model."""
    return ModelListResponse(
        data=[
            ModelObject(id=MODEL_ID, owned_by="catgpt"),
        ]
    )


@openai_router.post("/v1/images/generations", response_model=ImagesResponse)
async def create_image(
    request: ImageGenerationRequest,
) -> ImagesResponse:
    """
    OpenAI-compatible image generation endpoint.

    Sends the prompt to ChatGPT which uses DALL-E to generate images.
    Downloads the generated images and returns them in OpenAI format.
    Supports response_format='b64_json' (default) or 'url' (local file path).
    """
    import base64

    if not request.prompt:
        raise HTTPException(status_code=400, detail="prompt cannot be empty")

    client = _get_client()

    async with _lock:
        start_time = time.time()

        # Build an image-generation prompt.
        # n > 1: we ask ChatGPT to generate multiple images
        # size/quality/style hints are included but ChatGPT web may ignore them.
        prompt_parts = [f"Generate an image: {request.prompt}"]
        if request.n and request.n > 1:
            prompt_parts.append(f"Please generate {request.n} different images.")
        if request.size and request.size != "1024x1024":
            prompt_parts.append(f"Image size: {request.size}.")
        if request.quality == "hd":
            prompt_parts.append("Make it high-definition / highly detailed.")
        if request.style == "natural":
            prompt_parts.append("Use a natural, realistic style.")

        full_prompt = " ".join(prompt_parts)

        log.info(
            f"POST /v1/images/generations - prompt='{request.prompt[:80]}', "
            f"n={request.n}, size={request.size}, response_format={request.response_format}"
        )

        # Send to ChatGPT
        try:
            result = await client.send_message(full_prompt)
        except Exception as e:
            log.error(f"ChatGPT error during image generation: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"ChatGPT error: {str(e)}")

        elapsed_ms = int((time.time() - start_time) * 1000)

        # Check if ChatGPT generated images
        if not result.images:
            # ChatGPT may have responded with text instead of generating an image.
            # This can happen when the model declines or gives a text description.
            log.warning(
                f"No images detected in response ({elapsed_ms}ms). "
                f"ChatGPT replied: {result.message[:200]}"
            )
            raise HTTPException(
                status_code=422,
                detail=(
                    f"ChatGPT did not generate an image. "
                    f"Model response: {result.message[:500]}"
                ),
            )

        # Build image data objects
        image_data_list: list[ImageData] = []
        for img_info in result.images:
            revised_prompt = img_info.prompt_title or img_info.alt or request.prompt

            if request.response_format == "b64_json":
                # Read the downloaded file and base64-encode it
                if img_info.local_path:
                    try:
                        with open(img_info.local_path, "rb") as f:
                            img_bytes = f.read()
                        b64 = base64.b64encode(img_bytes).decode("utf-8")
                        image_data_list.append(
                            ImageData(
                                b64_json=b64,
                                revised_prompt=revised_prompt,
                            )
                        )
                    except Exception as e:
                        log.error(f"Failed to read image file {img_info.local_path}: {e}")
                else:
                    log.warning(f"Image has no local_path: {img_info.url[:80]}")
            else:
                # response_format == "url" - return local file path as URL
                image_data_list.append(
                    ImageData(
                        url=img_info.local_path or img_info.url,
                        revised_prompt=revised_prompt,
                    )
                )

        if not image_data_list:
            raise HTTPException(
                status_code=500,
                detail="Images were detected but could not be processed.",
            )

        log.info(
            f"Image generation complete: {len(image_data_list)} image(s), "
            f"{elapsed_ms}ms, format={request.response_format}"
        )

        return ImagesResponse(data=image_data_list)


@openai_router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(
    request: ChatCompletionRequest,
) -> ChatCompletionResponse:
    """
    OpenAI-compatible chat completions endpoint.

    Converts the message array into a single prompt, sends it to ChatGPT
    via browser automation, and returns an OpenAI-formatted response.
    Supports tool/function calling via prompt injection.
    """
    # -- Validate --------------------------------------------
    if request.stream:
        raise HTTPException(
            status_code=400,
            detail="Streaming is not supported. Set stream=false or omit it.",
        )

    if not request.messages:
        raise HTTPException(status_code=400, detail="messages array cannot be empty")

    return await _execute_chat_completion(request)


async def _execute_chat_completion(request: ChatCompletionRequest) -> ChatCompletionResponse:
    """Shared sync/async executor for chat completions."""
    client = _get_client()

    async with _lock:
        start_time = time.time()
        app_key = (request.user or "").strip() if request.user else ""
        explicit_thread_id = (request.thread_id or "").strip() if getattr(request, "thread_id", None) else ""

        if explicit_thread_id:
            current_tid = client._extract_thread_id()
            if current_tid != explicit_thread_id:
                log.info(f"OpenAI route: navigating to explicit thread {explicit_thread_id}")
                await client.navigate_to_thread(explicit_thread_id)
        elif Config.API_APP_THREAD_MODE and app_key:
            now_app = time.time()
            mapped_thread = ""
            async with _app_thread_lock:
                _prune_app_threads(now_app)
                mapped = _app_threads.get(app_key)
                if mapped:
                    mapped_thread = mapped[1]
            if mapped_thread:
                current_tid = client._extract_thread_id()
                if current_tid != mapped_thread:
                    log.info(f"OpenAI app-thread mode: app='{app_key}' -> thread {mapped_thread}")
                    await client.navigate_to_thread(mapped_thread)

        # -- Build the prompt --------------------------------
        messages = list(request.messages)

        # If tools are provided, inject tool definitions as a system prompt
        if request.tools:
            tool_system = _build_tool_system_prompt(request.tools)
            # Prepend as the first system message
            messages.insert(0, ChatMessage(role="system", content=tool_system))

        # If structured output is requested, force strict JSON response
        response_format_system = _build_response_format_system_prompt(request.response_format)
        if response_format_system and not _has_equivalent_response_instruction(messages, response_format_system):
            messages.insert(0, ChatMessage(role="system", content=response_format_system))

        messages = _dedupe_system_messages(messages)
        system_texts = [_extract_content_text(m.content) for m in messages if m.role == "system"]
        system_lengths = [len(t) for t in system_texts]
        system_previews = [_normalize_instruction_text(t)[:120] for t in system_texts]
        non_system = [m for m in messages if m.role != "system"]
        full_prompt = _build_prompt(messages)
        prompt = full_prompt
        used_thread_contract = False
        current_thread_id = client._extract_thread_id()
        contract_id = ""

        if (
            Config.API_THREAD_CONTRACT_MODE
            and system_texts
            and len(non_system) == 1
            and non_system[0].role == "user"
        ):
            contract_id = _contract_hash(system_texts)
            if current_thread_id:
                now_contract = time.time()
                async with _contract_lock:
                    _prune_thread_contracts(now_contract)
                    known = _thread_contracts.get(current_thread_id)
                    if known and known[1] == contract_id:
                        user_text = _extract_content_text(non_system[0].content)
                        prompt = _build_contract_reminder_prompt(user_text, contract_id)
                        used_thread_contract = True
                        _thread_contracts[current_thread_id] = (now_contract, contract_id)

        system_chars = sum(len(_extract_content_text(m.content)) for m in messages if m.role == "system")
        user_chars = sum(len(_extract_content_text(m.content)) for m in messages if m.role == "user")
        assistant_chars = sum(len(_extract_content_text(m.content)) for m in messages if m.role == "assistant")
        tool_chars = sum(len(_extract_content_text(m.content)) for m in messages if m.role == "tool")
        log.debug(
            "System prompt breakdown: count=%d lengths=%s previews=%s",
            len(system_texts),
            system_lengths,
            system_previews,
        )
        log.info(
            f"POST /v1/chat/completions - model={request.model}, "
            f"{len(request.messages)} messages, prompt={len(prompt)} chars "
            f"(system={system_chars}, user={user_chars}, assistant={assistant_chars}, tool={tool_chars})"
        )
        if used_thread_contract:
            log.info("Thread contract mode: compact prompt used for thread=%s", current_thread_id or "unknown")

        cache_key = _cache_key_for_request(request)
        now = time.time()
        async with _cache_lock:
            _prune_cache(now)
            cached_entry = _response_cache.get(cache_key)
            if cached_entry and now - cached_entry[0] <= _CACHE_TTL_SECONDS:
                log.info("Response cache hit: returning cached completion")
                return _clone_cached_response(cached_entry[1])

        # -- Extract attachments from messages --------------
        image_paths: list[str] = []
        file_paths: list[str] = []
        for msg in request.messages:
            if msg.role == "user" and isinstance(msg.content, list):
                image_urls = _extract_image_urls(msg.content)
                for url in image_urls:
                    local_path = await _download_file(url)
                    if local_path:
                        image_paths.append(local_path)

                file_attachments = _extract_file_attachments(msg.content)
                for fa in file_attachments:
                    local_path = await _download_file(fa)
                    if local_path:
                        file_paths.append(local_path)

        all_attachment_paths = image_paths + file_paths
        if all_attachment_paths:
            log.info(f"Extracted {len(image_paths)} image(s) and {len(file_paths)} file(s) from request")

        # -- Send to ChatGPT --------------------------------
        try:
            result = await client.send_message(
                prompt,
                image_paths=image_paths or None,
                file_paths=file_paths or None,
            )
        except Exception as e:
            log.error(f"ChatGPT error: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"ChatGPT error: {str(e)}")

        if Config.API_THREAD_CONTRACT_MODE and contract_id:
            thread_for_contract = result.thread_id or current_thread_id or client._extract_thread_id()
            if thread_for_contract:
                async with _contract_lock:
                    _prune_thread_contracts(time.time())
                    _thread_contracts[thread_for_contract] = (time.time(), contract_id)

        if Config.API_APP_THREAD_MODE and app_key:
            thread_for_app = result.thread_id or client._extract_thread_id()
            if thread_for_app:
                async with _app_thread_lock:
                    _prune_app_threads(time.time())
                    _app_threads[app_key] = (time.time(), thread_for_app)

        response_text = result.message
        elapsed_ms = int((time.time() - start_time) * 1000)

        if used_thread_contract and request.response_format and _extract_json_payload(response_text) is None:
            log.warning("Thread contract mode produced non-JSON content. Retrying once with full prompt.")
            try:
                full_retry = await client.send_message(
                    full_prompt,
                    image_paths=image_paths or None,
                    file_paths=file_paths or None,
                )
                response_text = full_retry.message
                elapsed_ms = int((time.time() - start_time) * 1000)
            except Exception as e:
                log.warning(f"Full-prompt fallback after contract mode failed: {e}")

        # -- Detect echo (extraction grabbed sent prompt instead of reply) --
        if response_text and "[System instruction:" in response_text and request.tools:
            log.warning("Response appears to echo the sent prompt - retrying extraction")
            try:
                await asyncio.sleep(3)
                from src.chatgpt.detector import extract_last_response_via_copy

                retry_text = await extract_last_response_via_copy(client.page)
                if retry_text and "[System instruction:" not in retry_text:
                    response_text = retry_text
                    log.info(f"Retry extraction succeeded: {len(response_text)} chars")
                else:
                    log.warning("Retry extraction still echoed - stripping system prefix")
                    idx = response_text.rfind("\n\n")
                    if idx > 0:
                        tail = response_text[idx:].strip()
                        if tail and not tail.startswith("["):
                            response_text = tail
            except Exception as e:
                log.warning(f"Retry extraction failed: {e}")

        # -- Check for tool calls ----------------------------
        tool_calls = None
        finish_reason = "stop"

        if request.response_format and response_text:
            response_text = _normalize_structured_content(response_text, request.response_format)
            mismatch = _structured_cardinality_mismatch(request.messages, response_text)
            if mismatch:
                expected, actual = mismatch
                log.warning(
                    "Structured cardinality mismatch detected (expected=%d, actual=%d). Retrying once.",
                    expected,
                    actual,
                )
                retry_prompt = _build_cardinality_retry_prompt(prompt, expected, actual)
                try:
                    retry_result = await client.send_message(
                        retry_prompt,
                        image_paths=image_paths or None,
                        file_paths=file_paths or None,
                    )
                    retry_text = retry_result.message
                    retry_text = _normalize_structured_content(retry_text, request.response_format)
                    retry_mismatch = _structured_cardinality_mismatch(request.messages, retry_text)
                    if not retry_mismatch:
                        response_text = retry_text
                        elapsed_ms = int((time.time() - start_time) * 1000)
                        log.info("Structured cardinality retry succeeded")
                    else:
                        log.warning(
                            "Structured cardinality retry still mismatched (expected=%d, actual=%d)",
                            retry_mismatch[0],
                            retry_mismatch[1],
                        )
                except Exception as e:
                    log.warning(f"Structured cardinality retry failed: {e}")

        if request.tools:
            tool_calls = _parse_tool_calls(response_text, request.tools)
            if tool_calls:
                finish_reason = "tool_calls"
                response_text = None

        # -- Build response ----------------------------------
        prompt_tokens = _estimate_tokens(prompt)
        completion_tokens = _estimate_tokens(response_text or "")

        response = ChatCompletionResponse(
            model=request.model,
            choices=[
                Choice(
                    index=0,
                    message=ChoiceMessage(
                        role="assistant",
                        content=response_text,
                        tool_calls=tool_calls,
                    ),
                    finish_reason=finish_reason,
                )
            ],
            usage=UsageInfo(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

        log.info(
            f"Response: {elapsed_ms}ms, finish_reason={finish_reason}, "
            f"tokens~{response.usage.total_tokens}"
        )

        async with _cache_lock:
            _prune_cache(time.time())
            _response_cache[cache_key] = (time.time(), response.model_copy(deep=True))

        return response


async def _run_async_chat_job(job_id: str, request: ChatCompletionRequest) -> None:
    """Background runner for async chat completion jobs."""
    async with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "running"

    try:
        response = await _execute_chat_completion(request)
        async with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.status = "completed"
                job.response = response
    except Exception as e:
        log.error(f"Async chat job failed ({job_id}): {e}", exc_info=True)
        async with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.status = "failed"
                job.error = str(e)


@openai_router.post("/v1/chat/completions/async", response_model=ChatCompletionJobResponse)
async def create_chat_completion_async(
    request: ChatCompletionAsyncRequest,
) -> ChatCompletionJobResponse:
    """Submit an async chat completion job and return the job handle."""
    if request.stream:
        raise HTTPException(
            status_code=400,
            detail="Streaming is not supported. Set stream=false or omit it.",
        )

    if not request.messages:
        raise HTTPException(status_code=400, detail="messages array cannot be empty")

    _get_client()

    job_id = f"chatjob-{uuid.uuid4().hex[:24]}"
    job = ChatCompletionJobResponse(
        id=job_id,
        status="queued",
        model=request.model,
    )

    async with _jobs_lock:
        _jobs[job_id] = job

    asyncio.create_task(_run_async_chat_job(job_id, request))
    return job


@openai_router.get("/v1/chat/completions/async/{job_id}", response_model=ChatCompletionJobResponse)
async def get_chat_completion_async_job(job_id: str) -> ChatCompletionJobResponse:
    """Get async chat completion job state and result."""
    async with _jobs_lock:
        job = _jobs.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return job
