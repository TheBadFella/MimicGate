"""
Centralized configuration — loads from .env with sensible defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*_args, **_kwargs) -> bool:
        return False

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

    SUPPORTED_PROVIDERS: tuple[str, ...] = ("chatgpt", "claude", "gemini", "minimax")

    # Paths
    PROJECT_ROOT: Path = _PROJECT_ROOT
    BROWSER_DATA_DIR: Path = _PROJECT_ROOT / os.getenv("BROWSER_DATA_DIR", "browser_data")
    LOG_DIR: Path = _PROJECT_ROOT / os.getenv("LOG_DIR", "logs")
    IMAGES_DIR: Path = _PROJECT_ROOT / os.getenv("IMAGES_DIR", "downloads/images")
    AUDIO_DIR: Path = _PROJECT_ROOT / os.getenv("AUDIO_DIR", "downloads/audio")

    # Browser
    HEADLESS: bool = os.getenv("HEADLESS", "false").lower() == "true"
    SLOW_MO: int = int(os.getenv("SLOW_MO", "25"))
    # Parallel ChatGPT/Claude tabs. Same-session requests stay serial.
    MAX_CONCURRENT_REQUESTS: int = max(1, int(os.getenv("MAX_CONCURRENT_REQUESTS", "3")))
    MAX_ACTIVE_TABS: int = max(1, int(os.getenv("MAX_ACTIVE_TABS", "4")))
    BROWSER_CHANNEL: str = os.getenv("BROWSER_CHANNEL", "chrome").strip().lower()
    CHATGPT_URL: str = os.getenv("CHATGPT_URL", "https://chatgpt.com")
    CHATGPT_PROJECT_URL: str = os.getenv("CHATGPT_PROJECT_URL", "").strip()
    CLAUDE_URL: str = os.getenv("CLAUDE_URL", "https://claude.ai")
    GEMINI_URL: str = os.getenv("GEMINI_URL", "https://gemini.google.com")
    GEMINI_DEFAULT_MODEL: str = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-3.8-flash")
    GEMINI_MODEL_ALIASES: str = os.getenv(
        "GEMINI_MODEL_ALIASES",
        "gemini-3.8-flash=3.8 Flash|Flash,gemini-3.6-flash=3.6 Flash|Flash,gemini-3.5-flash-lite=3.5 Flash-Lite,gemini-3.1-pro=3.1 Pro|Pro,gemini-extended-thinking=Extended thinking|Thinking",
    )
    GEMINI_LONG_PROMPT_FALLBACK: str = os.getenv(
        "GEMINI_LONG_PROMPT_FALLBACK", "attachment"
    )
    GEMINI_LONG_PROMPT_THRESHOLD: int = max(
        0, int(os.getenv("GEMINI_LONG_PROMPT_THRESHOLD", "0"))
    )
    MINIMAX_BASE_URLS: dict[str, str] = {
        "global_en": "https://api.minimax.io/v1",
        "cn_zh": "https://api.minimaxi.com/v1",
    }
    MINIMAX_REGION: str = os.getenv("MINIMAX_REGION", "global_en").lower()
    MINIMAX_BASE_URL: str = (
        os.getenv("MINIMAX_BASE_URL", "").strip()
        or MINIMAX_BASE_URLS.get(MINIMAX_REGION, MINIMAX_BASE_URLS["global_en"])
    ).rstrip("/")
    MINIMAX_API_KEY: str = os.getenv("MINIMAX_API_KEY", "").strip()
    MINIMAX_MODEL_IDS: tuple[str, ...] = ("MiniMax-M2.7",)
    MINIMAX_MODEL: str = os.getenv("MINIMAX_MODEL", MINIMAX_MODEL_IDS[0]).strip()
    CHATGPT_DEFAULT_MODEL: str = os.getenv("CHATGPT_DEFAULT_MODEL", "")
    CHATGPT_MODEL_ALIASES: str = os.getenv(
        "CHATGPT_MODEL_ALIASES",
        "gpt-5.6-sol=GPT-5.6 Sol|5.6 Sol|Instant,gpt-5.6-sol-medium=GPT-5.6 Sol|5.6 Sol,gpt-5.6-sol-high=GPT-5.6 Sol|5.6 Sol,gpt-5.6-sol-extra-high=GPT-5.6 Sol|5.6 Sol,gpt-5.6-sol-pro=GPT-5.6 Sol|5.6 Sol|Pro,gpt-5.5=GPT-5.5|5.5,gpt-5.5-medium=GPT-5.5|5.5,gpt-5.5-high=GPT-5.5|5.5,gpt-5.5-thinking=GPT-5.5|5.5|Thinking|5.5 Thinking,gpt-5.5-extra-high=GPT-5.5|5.5,gpt-5.5-pro=GPT-5.5|5.5|5.5 Pro",
    )
    CHATGPT_MODEL_SETTINGS: str = os.getenv(
        "CHATGPT_MODEL_SETTINGS",
        "gpt-5.6-sol=Instant,gpt-5.6-sol-medium=Medium,gpt-5.6-sol-high=High,gpt-5.6-sol-extra-high=Extra High,gpt-5.6-sol-pro=Pro,gpt-5.5=Instant,gpt-5.5-medium=Medium,gpt-5.5-high=High,gpt-5.5-thinking=High,gpt-5.5-extra-high=Extra High,gpt-5.5-pro=Pro",
    )
    CHATGPT_MODEL_SWITCH_TIMEOUT: int = int(os.getenv("CHATGPT_MODEL_SWITCH_TIMEOUT", "10000"))
    CHATGPT_MODEL_SWITCH_STRICT: bool = os.getenv("CHATGPT_MODEL_SWITCH_STRICT", "false").lower() == "true"
    CHATGPT_MODEL_DISCOVERY_TTL_SECONDS: int = int(os.getenv("CHATGPT_MODEL_DISCOVERY_TTL_SECONDS", "600"))
    # Browser UI-driven long-prompt fallback.  The threshold is optional because
    # ChatGPT's effective composer limit can vary by model/account.
    CHATGPT_LONG_PROMPT_FALLBACK: str = os.getenv(
        "CHATGPT_LONG_PROMPT_FALLBACK", "attachment"
    ).strip().lower()
    CHATGPT_LONG_PROMPT_THRESHOLD: int = max(
        0, int(os.getenv("CHATGPT_LONG_PROMPT_THRESHOLD", "0"))
    )
    ATTACHMENT_EXPAND_MULTIPAGE: bool = os.getenv("ATTACHMENT_EXPAND_MULTIPAGE", "true").lower() == "true"
    ATTACHMENT_MAX_PAGES: int = int(os.getenv("ATTACHMENT_MAX_PAGES", "24"))
    ATTACHMENT_RENDER_DPI: int = int(os.getenv("ATTACHMENT_RENDER_DPI", "144"))
    OLLAMA_EMBEDDING_MODELS: str = os.getenv("OLLAMA_EMBEDDING_MODELS", "nomic-embed-text")
    OLLAMA_EMBEDDING_DIMENSIONS: int = int(os.getenv("OLLAMA_EMBEDDING_DIMENSIONS", "768"))
    OLLAMA_ACTIVE_MODEL_TTL_SECONDS: int = int(os.getenv("OLLAMA_ACTIVE_MODEL_TTL_SECONDS", "900"))

    # Provider selection
    PROVIDER: str = os.getenv("PROVIDER", "chatgpt").lower()

    @classmethod
    def provider_url(cls) -> str:
        """Return the target URL for the active provider."""
        if cls.PROVIDER == "claude":
            return cls.CLAUDE_URL
        if cls.PROVIDER == "gemini":
            base = (cls.GEMINI_URL or "https://gemini.google.com").rstrip("/")
            return base if base.endswith("/app") else f"{base}/app"
        if cls.PROVIDER == "minimax":
            return cls.MINIMAX_BASE_URL
        return cls.CHATGPT_URL

    @classmethod
    def chatgpt_project_url(cls) -> str:
        """Return a validated optional ChatGPT project-root URL."""
        value = (cls.CHATGPT_PROJECT_URL or "").strip().rstrip("/")
        if not value:
            return ""
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        path = parsed.path.rstrip("/")
        if parsed.scheme not in {"http", "https"} or host not in {"chatgpt.com", "www.chatgpt.com"}:
            raise ValueError("CHATGPT_PROJECT_URL must use https://chatgpt.com")
        if not path.startswith("/g/g-p-") or not path.endswith("/project"):
            raise ValueError("CHATGPT_PROJECT_URL must be a ChatGPT project URL ending in /project")
        return f"https://chatgpt.com{path}"

    @classmethod
    def provider_name(cls) -> str:
        """Return the display name for the active provider."""
        names = {
            "chatgpt": "ChatGPT",
            "claude": "Claude",
            "gemini": "Gemini",
            "minimax": "MiniMax",
        }
        return names.get(cls.PROVIDER, cls.PROVIDER)

    @classmethod
    def validate_provider(cls) -> None:
        """Validate provider-specific configuration before startup."""
        if cls.PROVIDER not in cls.SUPPORTED_PROVIDERS:
            supported = ", ".join(cls.SUPPORTED_PROVIDERS)
            raise ValueError(
                f"Unsupported provider '{cls.PROVIDER}'. Choose one of: {supported}"
            )
        if cls.PROVIDER == "minimax":
            base_url_override = os.getenv("MINIMAX_BASE_URL", "").strip()
            if (
                cls.MINIMAX_REGION not in cls.MINIMAX_BASE_URLS
                and not base_url_override
            ):
                supported = ", ".join(cls.MINIMAX_BASE_URLS)
                raise ValueError(
                    f"Unsupported MiniMax region '{cls.MINIMAX_REGION}'. "
                    f"Choose one of: {supported}"
                )
            if cls.MINIMAX_MODEL not in cls.MINIMAX_MODEL_IDS:
                supported = ", ".join(cls.MINIMAX_MODEL_IDS)
                raise ValueError(
                    f"Unsupported MiniMax model '{cls.MINIMAX_MODEL}'. "
                    f"Choose one of: {supported}"
                )

    @classmethod
    def uses_browser(cls) -> bool:
        """Return whether the active provider requires browser automation."""
        return cls.PROVIDER != "minimax"

    @classmethod
    def provider_model_ids(cls) -> tuple[str, ...]:
        """Return model IDs exposed by the active provider."""
        if cls.PROVIDER == "claude":
            return ("claude-browser",)
        if cls.PROVIDER == "gemini":
            from src.gemini.model_registry import list_gemini_model_ids
            return list_gemini_model_ids()
        if cls.PROVIDER == "minimax":
            return cls.MINIMAX_MODEL_IDS
        return ("catgpt-browser",)

    @classmethod
    def default_model_id(cls) -> str:
        """Return the default model ID for the active provider."""
        if cls.PROVIDER == "gemini":
            return cls.GEMINI_DEFAULT_MODEL or "gemini-browser"
        if cls.PROVIDER == "minimax":
            return cls.MINIMAX_MODEL
        return cls.provider_model_ids()[0]

    @classmethod
    def resolve_model_id(cls, requested: str | None) -> str:
        """Resolve request defaults and validate MiniMax model IDs."""
        if cls.PROVIDER != "minimax":
            return requested or cls.default_model_id()

        if not requested or requested in {"catgpt-browser", "claude-browser", "gemini-browser"}:
            return cls.MINIMAX_MODEL
        if requested not in cls.MINIMAX_MODEL_IDS:
            supported = ", ".join(cls.MINIMAX_MODEL_IDS)
            raise ValueError(
                f"Unsupported MiniMax model '{requested}'. Choose one of: {supported}"
            )
        return requested

    @classmethod
    def provider_owner(cls) -> str:
        """Return the owner label used by the models endpoint."""
        owners = {
            "chatgpt": "catgpt",
            "claude": "anthropic",
            "gemini": "google",
            "minimax": "minimax",
        }
        return owners.get(cls.PROVIDER, cls.PROVIDER)

    @classmethod
    def supports_image_generation(cls) -> bool:
        """Return whether the active provider supports the image route."""
        return cls.PROVIDER == "chatgpt"

    # Timeouts (ms)
    RESPONSE_TIMEOUT: int = int(os.getenv("RESPONSE_TIMEOUT", "120000"))
    SELECTOR_TIMEOUT: int = int(os.getenv("SELECTOR_TIMEOUT", "10000"))

    # Human simulation (ms)
    TYPING_SPEED_MIN: int = int(os.getenv("TYPING_SPEED_MIN", "50"))
    TYPING_SPEED_MAX: int = int(os.getenv("TYPING_SPEED_MAX", "150"))
    THINKING_PAUSE_MIN: int = int(os.getenv("THINKING_PAUSE_MIN", "500"))
    THINKING_PAUSE_MAX: int = int(os.getenv("THINKING_PAUSE_MAX", "1500"))
    # Completion poll interval — how often to check if response is ready (ms)
    POLL_INTERVAL_MS: int = int(os.getenv("POLL_INTERVAL_MS", "300"))

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
    # If true, delete expired app-thread ChatGPT conversations from the browser UI
    API_APP_THREAD_DELETE_EXPIRED: bool = os.getenv("API_APP_THREAD_DELETE_EXPIRED", "false").lower() == "true"
    API_CONVERSATION_DB: Path = _PROJECT_ROOT / os.getenv(
        "API_CONVERSATION_DB", "state/conversations.sqlite3"
    )
    API_CONVERSATION_RETENTION_SECONDS: int = int(
        os.getenv("API_CONVERSATION_RETENTION_SECONDS", "2592000")
    )
    API_CONVERSATION_MAX_ROUTES: int = int(os.getenv("API_CONVERSATION_MAX_ROUTES", "10000"))
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
        cls.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
