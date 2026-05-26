"""
Centralized configuration — loads from .env with sensible defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

_CODE_ROOT = Path(__file__).resolve().parent.parent
_CWD = Path.cwd()

# Prefer the invocation directory as project root when running from
# a checkout (e.g. `nix run .#proxy` from repo root). Fall back to the
# code location (used for packaged/store execution).
if (_CWD / "src").exists() and (_CWD / "scripts").exists():
    _PROJECT_ROOT = _CWD
else:
    _PROJECT_ROOT = _CODE_ROOT

# Load .env from current working directory first, then from the
# resolved project root. Environment variables already set by the shell/systemd
# still win.
load_dotenv(_CWD / ".env")
load_dotenv(_PROJECT_ROOT / ".env")


class Config:
    """All project settings in one place."""

    # Paths
    PROJECT_ROOT: Path = _PROJECT_ROOT
    BROWSER_DATA_DIR: Path = _PROJECT_ROOT / os.getenv("BROWSER_DATA_DIR", "browser_data")
    LOG_DIR: Path = _PROJECT_ROOT / os.getenv("LOG_DIR", "logs")
    IMAGES_DIR: Path = _PROJECT_ROOT / os.getenv("IMAGES_DIR", "downloads/images")

    # Browser
    HEADLESS: bool = os.getenv("HEADLESS", "false").lower() == "true"
    SLOW_MO: int = int(os.getenv("SLOW_MO", "50"))
    CHATGPT_URL: str = os.getenv("CHATGPT_URL", "https://chatgpt.com")
    CLAUDE_URL: str = os.getenv("CLAUDE_URL", "https://claude.ai")
    CHATGPT_DEFAULT_MODEL: str = os.getenv("CHATGPT_DEFAULT_MODEL", "")
    CHATGPT_MODEL_ALIASES: str = os.getenv(
        "CHATGPT_MODEL_ALIASES",
        "gpt-5=GPT-5,gpt-5-mini=GPT-5 mini,gpt-5-nano=GPT-5 nano,gpt-5.3=GPT-5.3,o3=o3,o4-mini=o4-mini,gpt-4.5=GPT-4.5,gpt-4.1=GPT-4.1,gpt-4.1-mini=GPT-4.1 mini,gpt-4o=GPT-4o",
    )
    CHATGPT_MODEL_SWITCH_TIMEOUT: int = int(os.getenv("CHATGPT_MODEL_SWITCH_TIMEOUT", "10000"))
    ATTACHMENT_EXPAND_MULTIPAGE: bool = os.getenv("ATTACHMENT_EXPAND_MULTIPAGE", "true").lower() == "true"
    ATTACHMENT_MAX_PAGES: int = int(os.getenv("ATTACHMENT_MAX_PAGES", "24"))
    ATTACHMENT_RENDER_DPI: int = int(os.getenv("ATTACHMENT_RENDER_DPI", "144"))
    OLLAMA_EMBEDDING_MODELS: str = os.getenv("OLLAMA_EMBEDDING_MODELS", "nomic-embed-text")
    OLLAMA_EMBEDDING_DIMENSIONS: int = int(os.getenv("OLLAMA_EMBEDDING_DIMENSIONS", "768"))
    OLLAMA_ACTIVE_MODEL_TTL_SECONDS: int = int(os.getenv("OLLAMA_ACTIVE_MODEL_TTL_SECONDS", "900"))

    # Provider selection: "chatgpt" or "claude"
    PROVIDER: str = os.getenv("PROVIDER", "chatgpt").lower()

    @classmethod
    def provider_url(cls) -> str:
        """Return the target URL for the active provider."""
        if cls.PROVIDER == "claude":
            return cls.CLAUDE_URL
        return cls.CHATGPT_URL

    # Timeouts (ms)
    RESPONSE_TIMEOUT: int = int(os.getenv("RESPONSE_TIMEOUT", "120000"))
    SELECTOR_TIMEOUT: int = int(os.getenv("SELECTOR_TIMEOUT", "10000"))

    # Human simulation (ms)
    TYPING_SPEED_MIN: int = int(os.getenv("TYPING_SPEED_MIN", "50"))
    TYPING_SPEED_MAX: int = int(os.getenv("TYPING_SPEED_MAX", "150"))
    THINKING_PAUSE_MIN: int = int(os.getenv("THINKING_PAUSE_MIN", "500"))
    THINKING_PAUSE_MAX: int = int(os.getenv("THINKING_PAUSE_MAX", "1500"))
    # Completion poll interval — how often to check if response is ready (ms)
    POLL_INTERVAL_MS: int = int(os.getenv("POLL_INTERVAL_MS", "500"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    VERBOSE: bool = os.getenv("VERBOSE", "true").lower() == "true"

    # API (Phase 3)
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    # If true, requests without Bearer token are allowed even when API_TOKEN is set
    API_TOKEN_OPTIONAL: bool = os.getenv("API_TOKEN_OPTIONAL", "false").lower() == "true"
    # If true, cache large system instructions once per thread and send compact reminders after priming
    API_THREAD_CONTRACT_MODE: bool = os.getenv("API_THREAD_CONTRACT_MODE", "false").lower() == "true"
    API_THREAD_CONTRACT_TTL_SECONDS: int = int(os.getenv("API_THREAD_CONTRACT_TTL_SECONDS", "3600"))
    # If true, route OpenAI requests to app-specific threads using request.user as app key
    API_APP_THREAD_MODE: bool = os.getenv("API_APP_THREAD_MODE", "false").lower() == "true"
    API_APP_THREAD_TTL_SECONDS: int = int(os.getenv("API_APP_THREAD_TTL_SECONDS", "86400"))
    # If true, merge header-only rows (null fields + note/context text) into next item note/context
    API_HEADER_ROW_MERGE_MODE: bool = os.getenv("API_HEADER_ROW_MERGE_MODE", "false").lower() == "true"
    RATE_LIMIT_SECONDS: int = int(os.getenv("RATE_LIMIT_SECONDS", "5"))
    API_TOKEN: str = os.getenv("API_TOKEN", "")  # Bearer token for API auth (empty = no auth)

    # VNC
    VNC_PASSWORD: str = os.getenv("VNC_PASSWORD", "catgpt")

    # Viewport base (will be jittered ±20px)
    VIEWPORT_WIDTH: int = 1280
    VIEWPORT_HEIGHT: int = 720

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create required directories if they don't exist."""
        cls.BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOG_DIR.mkdir(parents=True, exist_ok=True)
        cls.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
