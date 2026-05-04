"""
Minimal Ollama-compatible request schemas.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class OllamaChatMessage(BaseModel):
    role: str = "user"
    content: str = ""
    images: Optional[list[str]] = None


class OllamaChatRequest(BaseModel):
    model: str
    messages: list[OllamaChatMessage] = Field(default_factory=list)
    stream: bool = False
    format: Optional[Any] = None
    keep_alive: Optional[Any] = None
    options: Optional[dict[str, Any]] = None


class OllamaGenerateRequest(BaseModel):
    model: str
    prompt: str = ""
    system: Optional[str] = None
    template: Optional[str] = None
    stream: bool = False
    raw: bool = False
    format: Optional[Any] = None
    keep_alive: Optional[Any] = None
    options: Optional[dict[str, Any]] = None
    context: Optional[list[int]] = None
    images: Optional[list[str]] = None


class OllamaEmbedRequest(BaseModel):
    model: str
    input: str | list[str]
    truncate: Optional[bool] = None
    options: Optional[dict[str, Any]] = None
    keep_alive: Optional[Any] = None


class OllamaShowRequest(BaseModel):
    model: str
    verbose: Optional[bool] = None


class OllamaPullRequest(BaseModel):
    model: str
    stream: bool = False


class OllamaDeleteRequest(BaseModel):
    model: Optional[str] = None
    name: Optional[str] = None


class OllamaCopyRequest(BaseModel):
    source: str
    destination: str

