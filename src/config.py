"""
Centralized configuration — loads from .env with sensible defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
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

    # Timeouts (ms)
    RESPONSE_TIMEOUT: int = int(os.getenv("RESPONSE_TIMEOUT", "120000"))
    SELECTOR_TIMEOUT: int = int(os.getenv("SELECTOR_TIMEOUT", "10000"))

    # Human simulation (ms)
    TYPING_SPEED_MIN: int = int(os.getenv("TYPING_SPEED_MIN", "50"))
    TYPING_SPEED_MAX: int = int(os.getenv("TYPING_SPEED_MAX", "150"))
    THINKING_PAUSE_MIN: int = int(os.getenv("THINKING_PAUSE_MIN", "1000"))
    THINKING_PAUSE_MAX: int = int(os.getenv("THINKING_PAUSE_MAX", "3000"))

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
