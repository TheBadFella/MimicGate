# Setup Guide

This guide covers every way to run MimicGate Gateway: Docker, local development, and Nix.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Docker Setup (recommended)](#docker-setup-recommended)
- [Local Setup (no Docker)](#local-setup-no-docker)
- [Nix Flake Setup](#nix-flake-setup)
- [Environment Variables](ENVIRONMENT_VARIABLES.md)
- [Gemini Provider Guide](GEMINI_PROVIDER_GUIDE.md)
- [First Login](#first-login)
- [Switching Providers](#switching-providers)
- [Authentication](#authentication)
- [Docker Internals](#docker-internals)
- [systemd Service (optional)](#systemd-service-optional)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

- **Python 3.9+** (local setup only)
- **Docker + Docker Compose** (Docker setup only)
- A **ChatGPT**, **Claude**, or **Gemini** account (free or paid)

---

## Docker Setup (recommended)

Docker runs the entire stack in one container: virtual display, VNC, browser, and API server.

```bash
# 1. Clone the repo
git clone https://github.com/TheBadFella/MimicGate.git
cd MimicGate

# 2. Create .env and set your own API and browser-GUI passwords
#    See docs/ENVIRONMENT_VARIABLES.md for every supported value.

# 3. Edit .env to pick your provider
#    Set PROVIDER=chatgpt, PROVIDER=claude, or PROVIDER=gemini

# 4. Build and start
docker compose up --build -d

# 5. First login (one-time) - open the browser UI
open http://localhost:5800
# Sign into ChatGPT, Claude, or Gemini in the browser window you see
# Close the web GUI tab when done; session is saved automatically

# 6. Verify it works
curl -H "Authorization: Bearer dummy123" http://localhost:8650/v1/models
# {"object":"list","data":[{"id":"claude-browser",...}]}

# 7. Send your first message
curl -X POST http://localhost:8650/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy123" \
  -d '{
    "model": "claude-browser",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

Minimal `.env`:

```dotenv
MIMICGATE_API_KEY=replace-me
MIMICGATE_VNC_PASSWORD=replace-me
MIMICGATE_USER_ID=1000
MIMICGATE_GROUP_ID=1000
```

### Docker Notes

- **Code is baked into the image.** After editing source files, rebuild:
  ```bash
  docker compose up --build -d   # rebuilds and restarts
  ```
  `docker restart mimicgate` does NOT pick up code changes.

- **Browser session persists** under `${DOCKERDIR}/appdata/mimicgate/browser`. You only need to log in once.

- **Logs** are bind-mounted under `${DOCKERDIR}/appdata/mimicgate/logs` on the host.

- **The jlesage web GUI** at `http://localhost:5800` lets you see and interact with the browser (useful for debugging, CAPTCHAs, or re-login). Default VNC password: `mimicgate`.

---

## Local Setup (no Docker)

```bash
# 1. Clone and enter the repo
git clone https://github.com/TheBadFella/MimicGate.git
cd MimicGate

# 2. Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Chromium for Patchright
patchright install chromium

# 5. Optionally create .env to override defaults
# See docs/ENVIRONMENT_VARIABLES.md; for example, set PROVIDER=claude

# 6. First login (one-time)
python scripts/first_login.py
# A browser window opens. Sign into your provider. Press Enter when done.

# 7. Start the API server
python -m src.api.server
# API is live at http://localhost:8000

# 8. (Optional) Start the terminal chat UI
python -m src.cli.app
```

---

## Nix Flake Setup

This repo ships a `flake.nix` that packages Patchright and matching Chromium revisions.

```bash
# 1. Optionally create .env to override defaults
# See docs/ENVIRONMENT_VARIABLES.md

# 2. First login (one-time, interactive)
nix run .#login

# 3. Start the proxy
nix run .#proxy

# 4. Optional: run the TUI
nix run .#tui
```

Notes:
- The app reads `./.env` from your current working directory if present.
- Shell environment variables override values from `.env`.

---

## First Login

MimicGate Gateway uses your existing browser session. You sign in **once** and the browser profile is persisted.

> **OAuth login note for ChatGPT and Claude:**
> Patchright/Chromium runs in a controlled automation context where Google's third-party OAuth ("Continue with Google") blocks logins to external services like ChatGPT or Claude.
> For ChatGPT and Claude, use email + password, Microsoft, Apple, or magic link / OTP instead.
>
> When using the **Google Gemini provider** (`PROVIDER=gemini`), you sign directly into your Google Account on `gemini.google.com`, which works normally. See the [Gemini Provider Guide](GEMINI_PROVIDER_GUIDE.md) for details.

### Docker

1. Start the container: `docker compose up --build -d`
2. Wait ~30 seconds for startup
3. Open **http://localhost:5800** in your browser
4. You will see a Chromium browser inside the VNC viewer
5. Sign into your provider using one of these methods:
   | Method | Works? |
   |---|---|
   | Email + password | Recommended |
   | Microsoft account | Works |
   | Apple ID | Works |
   | Magic link / OTP email | Works |
   | Direct Google Account (Gemini provider) | Works |
   | "Continue with Google" (ChatGPT / Claude) | Blocked by Google OAuth |
6. Verify you see the chat interface
7. Close the web GUI tab; your session is saved in the mounted browser directory and survives container restarts.

### Local

1. Run `python scripts/first_login.py`
2. A Chromium window opens and navigates to your provider
3. Sign in using your account credentials
4. Press Enter in the terminal when you see the chat page
5. The browser closes. Session is saved in `browser_data/` (or `browser_data_claude/`, `browser_data_gemini/`).

### Re-login

If your session expires (typically after days/weeks), repeat the login flow. The API returns a 503 error when the session is expired.

---

## Switching Providers

Edit your `.env` file:

```bash
# For Gemini
PROVIDER=gemini
BROWSER_DATA_DIR=./browser_data_gemini

# For Claude
PROVIDER=claude
BROWSER_DATA_DIR=./browser_data_claude

# For ChatGPT
PROVIDER=chatgpt
BROWSER_DATA_DIR=./browser_data
```

Each provider has its own browser data directory so your login sessions do not conflict. After switching, restart the server.

For Docker, also update the `PROVIDER` in `docker-compose.yml` under `environment:` and rebuild. See also the dedicated [Gemini Provider Guide](GEMINI_PROVIDER_GUIDE.md).

---

## Authentication

### API Bearer Token

All API endpoints require a Bearer token when `API_TOKEN` is set.

```bash
curl -H "Authorization: Bearer dummy123" http://localhost:8000/v1/models
```

With the OpenAI SDK or LangChain, pass the token as `api_key`:

```python
client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy123")
```

**Open paths** (no token required): `/docs`, `/redoc`, `/openapi.json`, `/healthz`

To disable auth, set `API_TOKEN=` (empty string) in `.env`.

### Web GUI Password

The jlesage browser UI at `http://localhost:5800` is password-protected.

Default: `mimicgate`. Change it via `VNC_PASSWORD` in `.env` or `docker-compose.yml`.

---

## Docker Internals

### Container Services (managed by jlesage/baseimage-gui)

| Service | Port | Purpose |
|---|---|---|
| Web GUI | `5800` | HTTP by default; HTTPS on the same port if `SECURE_CONNECTION=1` |
| Direct VNC | `5900` | Direct VNC client access (optional) |
| FastAPI | `8000` | API server (OpenAI-compatible + custom REST) |

### Startup Sequence

1. `50-mimicgate-init.sh` runs as root after jlesage initializes the application user:
   - Create and verify directories (`browser_data`, `logs`, `downloads/images`, `downloads/audio`)
   - Clean stale Chrome lock files
   - Pre-resolve DNS domains and write to `/etc/hosts` (Docker DNS workaround)
2. `jlesage/baseimage-gui` initializes X server, Openbox window manager, TigerVNC, and the web GUI
3. `/startapp.sh` launches `python3 -m src.api.server`
4. FastAPI server starts Patchright Chromium in the active graphical display

### Volumes

| Volume | Purpose |
|---|---|
| `${DOCKERDIR}/appdata/mimicgate/config:/config` | jlesage GUI configuration, certificates, and user home |
| `${DOCKERDIR}/appdata/mimicgate/browser:/app/browser_data` | Persistent browser session (cookies, login) |
| `${DOCKERDIR}/appdata/mimicgate/logs:/app/logs` | Logs accessible from host |

### Health Check

The container has a built-in health check hitting `/healthz` every 30 seconds.

```bash
docker inspect --format='{{.State.Health.Status}}' mimicgate
```

---

## systemd Service (optional)

For running as a background service with the Nix flake:

```ini
# ~/.config/systemd/user/mimicgate.service
[Unit]
Description=MimicGate Gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/Projects/MimicGate
ExecStart=/usr/bin/env nix run .#proxy
Restart=on-failure
RestartSec=5
Environment=HEADLESS=true
Environment=API_TOKEN=your-token-here
Environment=API_HOST=127.0.0.1
Environment=API_PORT=8000

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now mimicgate
journalctl --user -u mimicgate -f
```

---

## Troubleshooting

### "ChatGPT client not initialized" (503)

The browser hasn't finished starting. Wait 30-45 seconds after startup.

```bash
# Check logs
docker logs mimicgate --tail 50      # Docker
cat logs/api_server.log            # Local
```

### "Not logged in" / session expired

Re-login:
- Docker: Open http://localhost:5800 and sign in
- Local: Run `python scripts/first_login.py`

### Stale browser lock files

If the app crashes, orphan Chrome processes may leave lock files:

```bash
pkill -f "chrome-for-testing" 2>/dev/null
rm -f browser_data/SingletonLock browser_data/SingletonSocket browser_data/SingletonCookie
```

The app auto-cleans these on startup, but manual cleanup may be needed after hard crashes.

### Docker DNS issues

Chrome inside Docker sometimes fails to resolve domains. The entrypoint script pre-resolves domains via Python. If you still see DNS errors:

```bash
docker exec mimicgate cat /etc/hosts
docker exec mimicgate curl -s https://chatgpt.com
```

### Code changes not taking effect (Docker)

You must rebuild:

```bash
docker compose up --build -d   # correct
# NOT: docker restart mimicgate   # this uses the old image
```

### Services not running

```bash
docker exec mimicgate supervisorctl status
```

All 4 services (xvfb, vnc, novnc, mimicgate) should show `RUNNING`.
