"""
FastAPI server — serves ChatGPT as an API.

Launches the browser on startup, shuts it down on exit.

Usage:
    python -m src.api.server
    # or
    uvicorn src.api.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.browser.manager import BrowserManager
from src.browser.auto_login import ensure_logged_in
from src.chatgpt.client import ChatGPTClient
from src.config import Config
from src.api.routes import router, set_client
from src.api.openai_routes import openai_router, set_openai_client
from src.log import setup_logging

log = setup_logging("api_server", log_file="api_server.log")

# Global instances — needed for lifespan
_browser: BrowserManager | None = None
_client: ChatGPTClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: launch browser. Shutdown: close it."""
    global _browser, _client

    log.info("Starting browser for API server...")
    _browser = BrowserManager()
    page = await _browser.start()

    # Navigate with retries (DNS can be slow in Docker)
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            log.info(f"Navigation attempt {attempt}/{max_retries} to {Config.CHATGPT_URL}")
            await _browser.navigate(Config.CHATGPT_URL)
            break
        except Exception as e:
            log.warning(f"Navigation attempt {attempt} failed: {e}")
            if attempt == max_retries:
                log.error("All navigation attempts failed")
                raise
            wait_time = attempt * 5  # 5s, 10s, 15s, 20s
            log.info(f"Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)

    # Apply stealth patches AFTER the first navigation.
    # In Docker, applying stealth init scripts before navigation
    # causes Chrome's DNS resolver to fail (ERR_NAME_NOT_RESOLVED).
    await _browser.apply_stealth_patches()

    await asyncio.sleep(3)

    # ── Session info ─────────────────────────────────────────────
    session = await _browser.get_session_info()

    if not await _browser.is_logged_in():
        log.info("Not logged in — starting auto-login flow...")
        logged_in = await ensure_logged_in(_browser, has_session=session["exists"])
        if not logged_in:
            log.error("Login failed after auto-login attempt")
            raise RuntimeError("Could not log in to ChatGPT")
        # Refresh session info after login
        session = await _browser.get_session_info()

    _client = ChatGPTClient(page)
    set_client(_client, _browser)
    set_openai_client(_client)

    # ── Startup banner ───────────────────────────────────────────
    W = 60
    sep = "=" * W

    # Session details
    if session["exists"]:
        expires = session.get("expires")
        exp_str = expires.astimezone().strftime("%Y-%m-%d %H:%M %Z") if expires else "no expiry"
        email_str = session.get("email") or "unknown"
        session_line = f"  Account  : {email_str}"
        expiry_line  = f"  Expires  : {exp_str}"
        session_status = "ACTIVE SESSION"
    else:
        session_line = "  Account  : (no session)"
        expiry_line  = "  Expires  : —"
        session_status = "NO SESSION"

    # Runtime flags
    token_masked = ("*" * len(Config.API_TOKEN)) if Config.API_TOKEN else "(disabled)"
    flags = [
        f"  API token    : {token_masked}",
        f"  Headless     : {Config.HEADLESS}",
        f"  Log level    : {Config.LOG_LEVEL}",
        f"  Chatgpt URL  : {Config.CHATGPT_URL}",
        f"  Resp timeout : {Config.RESPONSE_TIMEOUT} ms",
    ]

    # Endpoints
    advertised_host = Config.API_ADVERTISE_HOST or Config.API_HOST
    advertised_port = Config.API_ADVERTISE_PORT or Config.API_PORT
    host = f"http://{advertised_host}:{advertised_port}"
    endpoints = [
        ("POST", f"{host}/v1/chat/completions", "Chat completions"),
        ("POST", f"{host}/v1/chat/completions/async", "Async chat submit"),
        ("GET ", f"{host}/v1/chat/completions/async/{{job_id}}", "Async chat status/result"),
        ("POST", f"{host}/v1/images/generations", "Image generation"),
        ("GET ", f"{host}/v1/models", "List models"),
        ("POST", f"{host}/chat", "Native chat"),
        ("POST", f"{host}/thread/new", "New thread"),
        ("GET ", f"{host}/threads", "List threads"),
        ("GET ", f"{host}/status", "Status"),
        ("GET ", f"{host}/healthz", "Health check (no auth)"),
        ("GET ", f"{host}/docs", "API docs (no auth)"),
    ]

    lines = [
        sep,
        "  CatGPT — READY".center(W),
        sep,
        f"  {session_status}",
        session_line,
        expiry_line,
        f"  Data dir : {Config.BROWSER_DATA_DIR}",
        "",
        "  RUNTIME FLAGS",
        *flags,
        "",
        "  ENDPOINTS",
        *[f"  {m}  {path:<42}  {desc}" for m, path, desc in endpoints],
        sep,
    ]

    for line in lines:
        log.info(line)


    yield  # Server is running

    log.info("Shutting down — closing browser...")
    await _browser.close()
    log.info("Browser closed")


app = FastAPI(
    title="CatGPT API",
    description=(
        "Browser automation API for ChatGPT. "
        "Sends messages via browser and returns responses."
    ),
    version="1.0.0",
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
)


def _custom_openapi():
    """Inject BearerAuth security scheme so Swagger UI shows the Authorize button."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema.setdefault("components", {})["securitySchemes"] = {
        "BearerAuth": {"type": "http", "scheme": "bearer"}
    }
    schema["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = _custom_openapi

# ── Bearer Token Auth Middleware ────────────────────────────────
class BearerTokenMiddleware(BaseHTTPMiddleware):
    """
    Require a Bearer token on all API requests when API_TOKEN is set.
    Skips auth for /docs, /openapi.json, and health-check paths.
    """

    OPEN_PATHS = {"/docs", "/redoc", "/openapi.json", "/healthz"}

    async def dispatch(self, request: Request, call_next):
        token = Config.API_TOKEN
        if not token:
            # No token configured — auth disabled
            return await call_next(request)

        path = request.url.path
        if path in self.OPEN_PATHS:
            return await call_next(request)

        # Check Authorization header
        auth_header = request.headers.get("authorization", "")
        if Config.API_TOKEN_OPTIONAL and not auth_header:
            # Optional-auth mode: no header is allowed.
            return await call_next(request)

        if auth_header.startswith("Bearer "):
            provided = auth_header[7:].strip()
        else:
            provided = ""

        expected = token.strip()
        if provided != expected:
            log.warning(f"Auth failed from {request.client.host if request.client else 'unknown'}: invalid token")
            return JSONResponse(
                status_code=401,
                content={"error": {"message": "Invalid or missing API token. Set Authorization: Bearer <API_TOKEN>", "type": "auth_error"}},
            )

        return await call_next(request)


app.add_middleware(BearerTokenMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(openai_router)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    """Unauthenticated health-check for Docker / load-balancers."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.server:app",
        host=Config.API_HOST,
        port=Config.API_PORT,
        log_level="info",
    )

