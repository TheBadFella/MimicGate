# CatGPT — ChatGPT Browser-Automation Gateway

> **A production-grade gateway that exposes the ChatGPT web UI as an OpenAI-compatible API.**
>
> Uses browser automation (Playwright / Patchright) to control a real ChatGPT session,
> supports **tool/function calling**, **image input**, **file attachments** (PDF, etc.),
> and **DALL-E image generation** — all without an OpenAI API key.

![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)
![Patchright](https://img.shields.io/badge/patchright-1.58%2B-green)
![FastAPI](https://img.shields.io/badge/fastapi-0.115%2B-orange)
![Docker](https://img.shields.io/badge/docker-compose-blue)

---

## Table of Contents

1. [What It Does](#what-it-does)
2. [Quick Start — Docker](#quick-start--docker-recommended)
3. [Quick Start — Local](#quick-start--local-without-docker)
4. [First Login (One-Time Setup)](#first-login-one-time-setup)
5. [Authentication](#authentication)
6. [API Reference](#api-reference)
   - [OpenAI-Compatible Endpoints](#openai-compatible-endpoints)
   - [Custom REST Endpoints](#custom-rest-endpoints)
   - [Health Check](#health-check)
7. [Usage Examples](#usage-examples)
   - [Simple Chat](#simple-chat)
   - [Tool / Function Calling](#tool--function-calling)
   - [Image Input (Vision)](#image-input-vision)
   - [File Attachments (PDF, DOCX, etc.)](#file-attachments-pdf-docx-etc)
   - [Combined: Images + Files + Tools](#combined-images--files--tools)
   - [Image Generation (DALL-E)](#image-generation-dall-e)
8. [TUI — Interactive Terminal Client](#tui--interactive-terminal-client)
9. [Configuration Reference](#configuration-reference)
10. [Architecture](#architecture)
11. [Project Structure](#project-structure)
12. [Docker Internals](#docker-internals)
13. [How It Works — Deep Dive](#how-it-works--deep-dive)
   - [Complicated Flows](#complicated-flows)
14. [Testing](#testing)
15. [Troubleshooting](#troubleshooting)
16. [Known Limitations](#known-limitations)
17. [Tech Stack](#tech-stack)

---

## What It Does

CatGPT automates a real browser session with ChatGPT, letting you:

- **Use ChatGPT as an OpenAI-compatible API** — drop-in replacement for `openai.ChatCompletion.create()`
- **Tool / Function calling** — full round-trip support (define tools → model calls them → send results back)
- **Send images** — OpenAI vision format (`image_url` with base64 data URLs or HTTP URLs)
- **Send file attachments** — PDF, DOCX, TXT, CSV, etc. via a custom `file` content type
- **Generate DALL-E images** — ask for images and they're auto-downloaded locally
- **Manage conversations** — create, switch, and list threads
- **Interactive TUI** — full-screen terminal chat interface with cyberpunk theme
- **Evade bot detection** — human-like typing, mouse movements, stealth patches, viewport jitter

All without needing an OpenAI API key — it uses your existing ChatGPT login session.

---

## Quick Start — Docker (Recommended)

Docker runs the entire stack (virtual display + VNC + browser + API) in one container.

```bash
# 1. Clone the repo
git clone <repo-url> catgpt && cd catgpt

# 2. Copy environment template
# Optional for local (non-Docker) runs: create a .env file with needed values
# (Docker deployments should configure environment variables in docker-compose.yml)

# 3. Build and start
docker compose up --build -d catgpt

# 4. First login — open noVNC in your browser
open http://localhost:6080
# → Log into ChatGPT in the browser you see in VNC
# → Once logged in, close the noVNC tab — your session is saved

# 5. Verify the API is ready (default token: dummy123)
curl -H "Authorization: Bearer dummy123" http://localhost:8000/v1/models

# 6. Send your first message
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy123" \
  -d '{
    "model": "catgpt-browser",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

> **After code changes**, you must rebuild the image — `docker restart catgpt` does NOT pick up changes:
>
> ```bash
> docker compose up --build -d catgpt
> ```

---

## Quick Start — Local (Without Docker)

```bash
# 1. Clone & setup
cd catgpt
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Install Chromium for Patchright
patchright install chromium

# 3. First login (one-time)
python scripts/first_login.py
# → A browser window opens. Log into ChatGPT. Press Enter in terminal when done.

# 4. Start the API server
python -m src.api.server
# → API available at http://localhost:8000

# 5. (Optional) Start the TUI
python -m src.cli.app
```

---

## First Login (One-Time Setup)

CatGPT uses your existing ChatGPT session. You need to sign in **once** — the browser profile is persisted.

### Docker Login Flow

1. Start the container: `docker compose up --build -d catgpt`
2. Wait ~30 seconds for startup
3. Open **http://localhost:6080** (noVNC) in your browser
4. You'll see a Chromium browser inside the VNC viewer
5. Navigate to chatgpt.com if not already there
6. Sign in with your ChatGPT account (Google, email, etc.)
7. Verify you see the ChatGPT new chat page
8. Close the noVNC tab — your session is saved in the Docker volume

### Local Login Flow

1. Run `python scripts/first_login.py`
2. A Chromium window opens and navigates to chatgpt.com
3. Sign in manually
4. Press Enter in the terminal when you see the chat page
5. The browser closes — session is saved in `browser_data/`

### Re-Login

If your session expires (typically after days/weeks), repeat the login flow. The API will return a 503 error if the session is expired.

---

## Authentication

### API Bearer Token

By default, all API endpoints require a Bearer token when `API_TOKEN` is set (default: `dummy123`).

```bash
curl -H "Authorization: Bearer dummy123" http://localhost:8000/v1/models
```

**OpenAI SDK / LangChain** — pass the token as the `api_key`:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="dummy123"  # your API_TOKEN value
)
```

**Open paths** (no token required): `/docs`, `/redoc`, `/openapi.json`, `/healthz`

To **disable** API auth entirely, set `API_TOKEN=` (empty string) in `docker-compose.yml` or `.env`.
To allow requests **with or without token** while still accepting token auth, set `API_TOKEN_OPTIONAL=true`.

### noVNC Password

The noVNC browser UI at `http://localhost:6080` is password-protected (default: `catgpt`).
Change it with `VNC_PASSWORD` in `docker-compose.yml`.

---

## API Reference

### OpenAI-Compatible Endpoints

Base URL: `http://localhost:8000/v1` — **Model ID:** `catgpt-browser`

| Method | Path                     | Description                                                                     |
| ------ | ------------------------ | ------------------------------------------------------------------------------- |
| `POST` | `/v1/chat/completions`   | Chat completions — tools, images, file attachments supported. **No streaming.** |
| `POST` | `/v1/chat/completions/async` | Submit async chat job (poll with job ID). Structured output supported.      |
| `GET`  | `/v1/chat/completions/async/{job_id}` | Get async job status/result (`queued/running/completed/failed`). |
| `POST` | `/v1/images/generations` | Generate images via DALL-E                                                      |
| `GET`  | `/v1/models`             | List available models (returns `catgpt-browser`)                                |
| `POST` | `/{app_name}/v1/chat/completions` | App-scoped chat completions (derives app from URL path)             |
| `POST` | `/{app_name}/v1/chat/completions/async` | App-scoped async chat submit                                      |
| `GET`  | `/{app_name}/v1/chat/completions/async/{job_id}` | App-scoped async status/result                           |
| `POST` | `/{app_name}/v1/images/generations` | App-scoped image generation                                        |
| `GET`  | `/{app_name}/v1/models` | App-scoped model list                                                       |

### Custom REST Endpoints

| Method | Path                | Description                                   |
| ------ | ------------------- | --------------------------------------------- |
| `POST` | `/chat`             | Send a message in the current conversation    |
| `POST` | `/thread/new`       | Start a new conversation with a first message |
| `POST` | `/thread/{id}/chat` | Send a message in a specific thread           |
| `GET`  | `/threads`          | List recent threads from sidebar              |
| `GET`  | `/status`           | Health check + login status + current thread  |

### Health Check

| Method | Path       | Description                                       |
| ------ | ---------- | ------------------------------------------------- |
| `GET`  | `/healthz` | Unauthenticated health check (used by Docker too) |

> **Streaming note:** `/v1/chat/completions` actively rejects `stream=true` with a 400 error. This is a fundamental limitation since the browser waits for the full ChatGPT response before returning.

> **Structured output note:** `response_format` is supported for `/v1/chat/completions` and `/v1/chat/completions/async` (including `json_object` and `json_schema`).

> **Response cache note:** `/v1/chat/completions` now includes an in-memory dedup cache for identical requests (TTL: 600s, max entries: 256). Cache hits return a fresh OpenAI-style response envelope (`id`, `created`) with cached content.

> **Prompt assembly note:** single-turn requests now include all provided `system` messages (not just the first one). Tool-mode prompt instructions were compacted to reduce repeated overhead.

> **App URL note:** You can use app-specific base URLs without proxy rewrites. Examples:
> `http://catgpt:8000/karakeep/v1`, `http://catgpt:8000/mealie/v1`,
> `http://catgpt:8000/linkwarden/v1`, `http://catgpt:8000/immich/v1`

---

## Usage Examples

### Simple Chat

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy123")

response = client.chat.completions.create(
    model="catgpt-browser",
    messages=[{"role": "user", "content": "What is quantum computing?"}]
)
print(response.choices[0].message.content)
```

```bash
# Or with curl:
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy123" \
  -d '{
    "model": "catgpt-browser",
    "messages": [{"role": "user", "content": "What is quantum computing?"}]
  }'
```

---

### Async Chat + Polling

```bash
# Submit job
curl -X POST http://localhost:8000/v1/chat/completions/async \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer dummy123" \
    -d '{
        "model": "catgpt-browser",
        "messages": [{"role": "user", "content": "Summarize this in 5 bullets"}]
    }'

# Response example:
# {"id":"chatjob-...","status":"queued", ...}

# Poll status/result
curl -H "Authorization: Bearer dummy123" \
    http://localhost:8000/v1/chat/completions/async/chatjob-REPLACE_ID
```

```python
import time
import requests

base = "http://localhost:8000/v1"
headers = {
    "Authorization": "Bearer dummy123",
    "Content-Type": "application/json",
}

submit = requests.post(
    f"{base}/chat/completions/async",
    headers=headers,
    json={
        "model": "catgpt-browser",
        "messages": [{"role": "user", "content": "Return only JSON with title and tags"}],
        "response_format": {"type": "json_object"},
    },
    timeout=30,
)
submit.raise_for_status()
job_id = submit.json()["id"]

while True:
    job = requests.get(
        f"{base}/chat/completions/async/{job_id}",
        headers={"Authorization": "Bearer dummy123"},
        timeout=30,
    )
    job.raise_for_status()
    payload = job.json()
    if payload["status"] in {"completed", "failed"}:
        print(payload)
        break
    time.sleep(1)
```

---

### Tool / Function Calling

Full round-trip tool calling — define tools, let the model call them, send results back.

```python
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"The weather in {city} is sunny, 25°C."

@tool
def add_numbers(a: int, b: int) -> str:
    """Add two numbers together."""
    return str(a + b)

llm = ChatOpenAI(
    model="catgpt-browser",
    base_url="http://localhost:8000/v1",
    api_key="dummy123",
)

llm_with_tools = llm.bind_tools([get_weather, add_numbers])
response = llm_with_tools.invoke([
    HumanMessage(content="What's the weather in Paris, and what is 42 + 58?")
])

# Model returns tool_calls
print(response.tool_calls)
# [{'name': 'get_weather', 'args': {'city': 'Paris'}, 'id': 'call_...'},
#  {'name': 'add_numbers', 'args': {'a': 42, 'b': 58}, 'id': 'call_...'}]

# Execute tools and send results back
messages = [HumanMessage(content="What's the weather in Paris, and what is 42 + 58?"), response]
for tc in response.tool_calls:
    tool_fn = {"get_weather": get_weather, "add_numbers": add_numbers}[tc["name"]]
    result = tool_fn.invoke(tc["args"])
    messages.append(ToolMessage(content=str(result), tool_call_id=tc["id"]))

final = llm_with_tools.invoke(messages)
print(final.content)
# "The weather in Paris is sunny at 25°C, and 42 + 58 = 100."
```

**How it works internally:** Tool definitions are injected as a system prompt instructing ChatGPT to output `{"tool_calls": [...]}` JSON. CatGPT parses that JSON and returns it in standard OpenAI `tool_calls` format. See [Tool Calling Implementation](#tool-calling-implementation) for details.

---

### Image Input (Vision)

Send images using the standard OpenAI vision format with base64 data URLs:

```python
import base64
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy123")

with open("photo.png", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

response = client.chat.completions.create(
    model="catgpt-browser",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this image in detail."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
        ]
    }]
)
print(response.choices[0].message.content)
```

**Multiple images** and **HTTP URLs** are also supported:

```python
# Multiple images
{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img1_b64}"}}
{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img2_b64}"}}

# HTTP URL (downloaded server-side)
{"type": "image_url", "image_url": {"url": "https://example.com/photo.jpg"}}
```

---

### File Attachments (PDF, DOCX, etc.)

CatGPT supports arbitrary file attachments via a custom `file` content type:

```python
import base64
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy123")

with open("document.pdf", "rb") as f:
    pdf_b64 = base64.b64encode(f.read()).decode()

response = client.chat.completions.create(
    model="catgpt-browser",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Summarize the contents of this PDF."},
            {
                "type": "file",
                "file": {
                    "filename": "document.pdf",
                    "data": pdf_b64,
                    "mime_type": "application/pdf"
                }
            },
        ]
    }]
)
```

**Supported file types:** PDF, DOCX, XLSX, TXT, CSV, JSON, and any other format ChatGPT accepts.

Alternative data-URL format:

```json
{
  "type": "file",
  "file": {
    "filename": "report.pdf",
    "url": "data:application/pdf;base64,<base64-encoded-content>"
  }
}
```

---

### Combined: Images + Files + Tools

All features can be used together in a single request:

```python
response = client.chat.completions.create(
    model="catgpt-browser",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Look at this image and PDF, then use add_numbers to add 10 + 20."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
            {"type": "file", "file": {"filename": "doc.pdf", "data": pdf_b64, "mime_type": "application/pdf"}},
        ]
    }],
    tools=[{
        "type": "function",
        "function": {
            "name": "add_numbers",
            "description": "Add two numbers",
            "parameters": {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}}
        }
    }]
)
```

---

### Image Generation (DALL-E)

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="dummy123")

response = client.images.generate(
    model="dall-e-3",
    prompt="A cyberpunk cat hacking a mainframe",
    n=1,
    size="1024x1024",
    response_format="b64_json",
)

image_data = response.data[0]
print(f"Revised prompt: {image_data.revised_prompt}")

import base64
with open("generated_image.png", "wb") as f:
    f.write(base64.b64decode(image_data.b64_json))
```

```bash
curl -X POST http://localhost:8000/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy123" \
  -d '{
    "model": "dall-e-3",
    "prompt": "A cyberpunk cat hacking a mainframe",
    "n": 1,
    "size": "1024x1024",
    "response_format": "b64_json"
  }'
```

**Request parameters:**

| Parameter         | Type    | Default      | Description                      |
| ----------------- | ------- | ------------ | -------------------------------- |
| `prompt`          | string  | _(required)_ | Text description of the image    |
| `model`           | string  | `dall-e-3`   | Ignored — uses ChatGPT's DALL-E  |
| `n`               | integer | `1`          | Number of images (1–4)           |
| `size`            | string  | `1024x1024`  | Hint to ChatGPT                  |
| `quality`         | string  | `standard`   | `standard` or `hd`               |
| `style`           | string  | `vivid`      | `vivid` or `natural`             |
| `response_format` | string  | `b64_json`   | `b64_json` or `url` (local path) |

> `size`, `quality`, and `style` are passed as hints in the prompt — the actual output depends on DALL-E's web UI.

---

## TUI — Interactive Terminal Client

CatGPT includes a full-screen cyberpunk-themed terminal chat interface built with Textual.

```bash
# Local only (not available inside Docker)
python -m src.cli.app
```

### Features

- Splash screen with ASCII cat logo
- Scrollable chat log with colored message borders (cyan = user, green = assistant, magenta = images)
- Markdown rendering in responses
- DALL-E image cards with file path and size
- Status bar: connection state, thread ID, message count, response time

### Commands

| Command        | Description                   |
| -------------- | ----------------------------- |
| `/new`         | Start a fresh conversation    |
| `/threads`     | List recent threads           |
| `/thread <id>` | Switch to a thread            |
| `/images`      | List downloaded DALL-E images |
| `/status`      | Connection details            |
| `/clear`       | Clear chat display            |
| `/help`        | Show commands                 |
| `/exit`        | Quit                          |

**Shortcuts:** `Ctrl+N` (new), `Ctrl+T` (threads), `Ctrl+L` (clear), `Ctrl+Q` (quit)

---

## Configuration Reference

All settings are loaded from environment variables (`.env` file or `docker-compose.yml`):

| Variable             | Default               | Description                                              |
| -------------------- | --------------------- | -------------------------------------------------------- |
| `BROWSER_DATA_DIR`   | `browser_data`        | Chrome persistent profile directory                      |
| `LOG_DIR`            | `logs`                | Log file output directory                                |
| `IMAGES_DIR`         | `downloads/images`    | DALL-E image download directory                          |
| `HEADLESS`           | `false`               | Run browser headless (not recommended — easily detected) |
| `SLOW_MO`            | `0`                   | Playwright slow-motion delay (ms) for debugging          |
| `CHATGPT_URL`        | `https://chatgpt.com` | Target ChatGPT URL                                       |
| `RESPONSE_TIMEOUT`   | `120000`              | Max wait for ChatGPT response (ms)                       |
| `SELECTOR_TIMEOUT`   | `5000`                | Timeout per selector probe (ms)                          |
| `TYPE_DELAY_MIN`     | `50`                  | Min delay between keystrokes (ms)                        |
| `TYPE_DELAY_MAX`     | `150`                 | Max delay between keystrokes (ms)                        |
| `THINK_PAUSE_MIN`    | `1000`                | Min thinking pause (ms)                                  |
| `THINK_PAUSE_MAX`    | `3000`                | Max thinking pause (ms)                                  |
| `LOG_LEVEL`          | `DEBUG`               | Logging level (DEBUG, INFO, WARNING, ERROR)              |
| `LOG_CONSOLE`        | `true`                | Enable console log output                                |
| `API_HOST`           | `0.0.0.0`             | FastAPI server bind address                              |
| `API_PORT`           | `8000`                | FastAPI server port                                      |
| `API_TOKEN`          | `dummy123`            | Bearer token for API auth (empty = disabled)             |
| `API_TOKEN_OPTIONAL` | `false`               | If `true`, requests without token are allowed even when `API_TOKEN` is set |
| `API_THREAD_CONTRACT_MODE` | `false`         | If `true`, reuses per-thread system instruction contracts with compact follow-up prompts |
| `API_THREAD_CONTRACT_TTL_SECONDS` | `3600`    | TTL for per-thread instruction contracts in memory       |
| `API_APP_THREAD_MODE` | `false`               | If `true`, routes requests to app-specific threads keyed by app identity (`user` first, then built-in app-name headers) |
| `API_APP_THREAD_TTL_SECONDS` | `86400`       | TTL for app-to-thread mappings in memory                 |
| `API_HEADER_ROW_MERGE_MODE` | `false`        | If `true`, merges header-only rows (note/context only) into the next item's note/context |
| `VNC_PASSWORD`       | `catgpt`              | Password for noVNC browser UI                            |
| `RATE_LIMIT_SECONDS` | `5`                   | Min seconds between API requests                         |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Docker Container                                │
│                                                                        │
│   ┌─────────┐   ┌──────────┐   ┌──────────────┐   ┌──────────────┐    │
│   │  Xvfb   │   │ x11vnc   │   │    noVNC     │   │   FastAPI    │    │
│   │ :99     │──▶│ VNC :5900│──▶│  WS :6080    │   │  API :8000   │    │
│   │(virtual │   │(captures │   │(web browser  │   │(OpenAI-compat│    │
│   │ display)│   │ display) │   │ access)      │   │  + custom)   │    │
│   └─────────┘   └──────────┘   └──────────────┘   └──────┬───────┘    │
│                                                           │            │
│                                          ┌────────────────┴──────┐     │
│                                          │   ChatGPTClient       │     │
│                                          │   (send_message,      │     │
│                                          │    new_chat,           │     │
│                                          │    _upload_files)      │     │
│                                          └────────────┬──────────┘     │
│                                                       │                │
│                          ┌────────────────────────────┼──────────┐     │
│                          │                            │          │     │
│                   ┌──────┴──────┐   ┌─────────────────┴┐  ┌─────┴──┐  │
│                   │  Detector   │   │  BrowserManager  │  │ Human  │  │
│                   │  (copy btn, │   │  (Patchright +   │  │ (type, │  │
│                   │   stop btn, │   │   stealth +      │  │  click,│  │
│                   │   stability)│   │   persistent ctx) │  │  delay)│  │
│                   └─────────────┘   └──────────────────┘  └────────┘  │
│                                                                        │
│   Managed by supervisord (4 processes)                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

**External clients** (Python, curl, LangChain, any OpenAI SDK) connect to port **8000** (API).\
**Developers** can connect to port **6080** (noVNC) to see/interact with the browser visually.

---

## Project Structure

```
catgpt/
├── README.md                     ← This file
├── requirements.txt              ← Python dependencies
├── docker-compose.yml            ← Single-service stack: ports 8000+6080, volumes
├── .env                          ← Local environment overrides (optional)
├── .dockerignore / .gitignore
│
├── docker/
│   ├── Dockerfile                ← Build: system deps + Python + Patchright
│   ├── entrypoint.sh             ← Container startup: Xvfb, DNS resolution, supervisor
│   └── supervisord.conf          ← Process manager: Xvfb + VNC + noVNC + FastAPI
│
├── src/
│   ├── config.py                 ← All settings loaded from env vars with defaults
│   ├── selectors.py              ← Centralized DOM selectors (single update point)
│   ├── log.py                    ← File + console logging setup
│   ├── dom_observer.py           ← DOM mutation observer (experimental)
│   ├── network_recorder.py       ← Network request recorder (experimental)
│   │
│   ├── browser/
│   │   ├── manager.py            ← Browser lifecycle: launch, persist, close, DNS
│   │   ├── stealth.py            ← Stealth patches: playwright-stealth + Docker workaround
│   │   ├── human.py              ← Human simulation: typing, clicking, delays, mouse
│   │   └── auto_login.py         ← Auto-login detection: prompts user if not logged in
│   │
│   ├── chatgpt/
│   │   ├── client.py             ← Core: send_message(), new_chat(), file upload
│   │   ├── detector.py           ← Response completion: copy btn, stop btn, text stability
│   │   ├── image_handler.py      ← DALL-E image detection, download, save
│   │   └── models.py             ← Data models: ChatResponse, ImageInfo, Thread
│   │
│   ├── api/
│   │   ├── server.py             ← FastAPI app: lifespan, browser init, CORS, routes
│   │   ├── openai_routes.py      ← OpenAI-compatible API: /v1/chat/completions, /v1/models
│   │   ├── openai_schemas.py     ← Pydantic schemas matching OpenAI's API spec
│   │   ├── routes.py             ← Custom REST API: /chat, /threads, /status
│   │   └── schemas.py            ← Custom API schemas
│   │
│   └── cli/
│       ├── app.py                ← Textual TUI: cyberpunk chat interface
│       └── catgpt.tcss           ← Terminal CSS theme
│
├── scripts/
│   ├── first_login.py            ← One-time browser sign-in script
│   ├── test_langchain_tools.py   ← Comprehensive test suite (6 test categories)
│   ├── test_phase1.py            ← Phase 1 validation
│   ├── test_multi_turn.py        ← Multi-turn conversation tests
│   ├── test_robust.py            ← Robustness test suite
│   ├── test_images.py            ← DALL-E image generation tests
│   └── debug_image_dom.py        ← DOM debugging utilities
│
├── downloads/                    ← Downloaded files & test assets
│   ├── images/                   ← DALL-E generated images + test images
│   └── test.pdf                  ← Test PDF for file attachment tests
│
├── browser_data/                 ← Persistent Chrome profile (gitignored)
├── logs/                         ← All log files (gitignored)
└── tests/                        ← Unit tests (placeholder)
```

---

## Docker Internals

### Container Services (managed by supervisord)

| Service    | Port            | Purpose                                   |
| ---------- | --------------- | ----------------------------------------- |
| **Xvfb**   | `:99` (display) | Virtual framebuffer — Chrome renders here |
| **x11vnc** | `5900`          | VNC server capturing the Xvfb display     |
| **noVNC**  | `6080`          | WebSocket bridge — browser-accessible VNC |
| **catgpt** | `8000`          | FastAPI API server                        |

### Startup Sequence (entrypoint.sh)

1. Create directories (`/app/browser_data`, `/app/logs`, `/app/downloads/images`)
2. Clean stale Chrome lock files (`SingletonLock`, `SingletonSocket`, `SingletonCookie`)
3. Set up VNC password from `VNC_PASSWORD` env var
4. Pre-resolve DNS domains via Python and write to `/etc/hosts` (Docker DNS workaround)
5. Log environment variables
6. Verify Xvfb functionality
7. Verify Patchright Chromium installation
8. Print access info (API URL, noVNC URL, first-login instructions)
9. Start supervisord (manages all 4 services)

### Volumes

| Volume                                                  | Purpose                                           |
| ------------------------------------------------------- | ------------------------------------------------- |
| `${DOCKERDIR}/appdata/catgpt/browser:/app/browser_data` | Persistent browser session (cookies, login state) |
| `${DOCKERDIR}/appdata/catgpt/logs:/app/logs`            | Logs accessible from host                         |

### Health Check

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/healthz"]
  interval: 30s
  timeout: 10s
  start_period: 60s
  retries: 3
```

The `/healthz` endpoint is unauthenticated so the health check works without a token.

---

## How It Works — Deep Dive

### Browser Lifecycle

1. **Launch:** `BrowserManager` creates a Patchright persistent browser context at `browser_data/`
2. **DNS Pre-resolution (Docker):** Pre-resolves `chatgpt.com`, `cdn.oaistatic.com`, etc. and passes them via `--host-resolver-rules`
3. **Navigate:** Opens `chatgpt.com` with retry logic (up to 5 attempts, exponential backoff)
4. **Stealth (deferred):** Stealth patches applied **after** first navigation to avoid breaking DNS
5. **Login Check:** `ensure_logged_in()` checks for login indicators and prompts if needed
6. **Client Injection:** `ChatGPTClient` is injected into all API routers
7. **Shutdown:** Browser closes gracefully on FastAPI shutdown

### Stealth & Anti-Detection

| Technique                 | Implementation                                                                          | File                 |
| ------------------------- | --------------------------------------------------------------------------------------- | -------------------- |
| Persistent Chrome profile | `launch_persistent_context()` — retains cookies, Cloudflare clearance                   | `browser/manager.py` |
| playwright-stealth        | Patches `navigator.webdriver`, WebGL, canvas, plugins                                   | `browser/stealth.py` |
| Docker stealth workaround | Uses `page.evaluate()` instead of `add_init_script()` (the latter breaks DNS in Docker) | `browser/stealth.py` |
| Human-like typing         | `keyboard.insert_text()` for paste-style input                                          | `browser/human.py`   |
| Mouse simulation          | Hover before click, natural movement                                                    | `browser/human.py`   |
| Random delays             | 500–1200ms before typing, 300–600ms before sending                                      | `browser/human.py`   |
| Viewport jitter           | ±20px randomization on each launch (1280×720 base)                                      | `browser/manager.py` |
| Headful mode              | Always runs with visible browser (headless is trivially detected)                       | `config.py`          |
| Lock file cleanup         | Auto-cleans stale `SingletonLock` files from crashed Chrome processes                   | `browser/manager.py` |
| Orphan process kill       | Kills leftover `chrome-for-testing` processes on startup                                | `browser/manager.py` |

> **Critical Docker DNS Fix:** `playwright-stealth`'s `add_init_script()` causes Chrome to fail DNS resolution inside Docker. The fix uses `page.evaluate()` to inject stealth JS at runtime instead, hooking `framenavigated` events to re-inject on every navigation.

### Message Send/Receive Flow

```
send_message(text, image_paths, file_paths)
│
├── 1. Count existing assistant messages (pre_count)
├── 2. Random delay (500-1200ms, human simulation)
├── 3. Upload files if any → _upload_files()
│      └── set_input_files() on hidden <input type="file">
│      └── Wait 3s + extra per file for processing
├── 4. Find chat input → _find_selector(CHAT_INPUT)
├── 5. Paste text → keyboard.insert_text()
├── 6. Random delay (300-600ms)
├── 7. Click send → _click_send() or fallback Enter key
├── 8. Wait for response → wait_for_response_complete()
│      └── Expected message count = pre_count + 1
├── 9. Sleep 1s (DOM settle)
├── 10. Check for DALL-E images → extract_images_from_response()
├── 11. Extract text:
│       ├── Image response → _extract_image_turn_text() (DOM scraping)
│       └── Text response → extract_last_response_via_copy() (copy button)
└── 12. Return ChatResponse(message, thread_id, elapsed_ms, images)
```

### Complicated Flows

#### 1) Async Chat Job Lifecycle (`/v1/chat/completions/async`)

```
POST /v1/chat/completions/async
│
├── 1. Validate request and resolve app key (if app-thread mode enabled)
├── 2. Create job entry: status=queued
├── 3. Store ownership map: job_id -> app_key
├── 4. Spawn background task (_run_async_chat_job)
└── 5. Return job handle immediately

Background task:
├── 6. Mark job status=running
├── 7. Execute normal chat pipeline (_execute_chat_completion)
├── 8a. On success: status=completed + response
└── 8b. On error:   status=failed + error

GET /v1/chat/completions/async/{job_id}
└── 9. Poll until completed/failed
```

#### 2) App-Thread Routing + Isolation

When `API_APP_THREAD_MODE=true`, CatGPT maps each app identity to its own ChatGPT thread:

```
Incoming request
│
├── 1. Derive app key (priority order):
│      endpoint app name -> request.user -> app headers -> origin/referer
│      -> user-agent fingerprint -> client IP fallback
├── 2. Check explicit request.thread_id:
│      └── If present, navigate there directly (overrides app mapping)
├── 3. Otherwise, look up app_key -> thread_id mapping
│      ├── Found: navigate to mapped thread
│      └── Missing: create a new chat to isolate this app
├── 4. Execute message send in that thread context
└── 5. Persist/refresh app_key -> resulting thread_id mapping (TTL-based)
```

This prevents multiple apps sharing one browser session from contaminating each
other's context.

#### 3) Thread Contract Compression (Large Instruction Prompts)

When `API_THREAD_CONTRACT_MODE=true`, repeated long instructions are compacted:

```
Request with system instructions + single user message
│
├── 1. Hash normalized system messages -> contract_id
├── 2. If current thread already learned same contract:
│      └── Replace full prompt with compact reminder + user payload
├── 3. Track previous user text in thread
├── 4. Detect repeated user instruction prefix (if any)
├── 5. If prefix contract is learned and response_format is active:
│      └── Use even smaller "user-prefix contract" reminder prompt
└── 6. On non-JSON result (when structured output requested):
       fallback retry once with full original prompt
```

This reduces token-like prompt size while keeping long-lived instruction
contracts stable across turns.

#### 4) Structured Output + Cardinality Recovery

For `response_format={"type":"json_schema"...}` or `{"type":"json_object"}`:

```
1. Inject strict structured-output system instruction (if not already present)
2. Send message and normalize extracted assistant text
3. Validate output cardinality against request expectation
4. If mismatch, build retry prompt with expected vs actual counts
5. Retry once and accept retry if cardinality now matches
```

This addresses common browser-UI model behavior where valid JSON is returned but
with the wrong number of items.

### Response Detection Strategy

The detector (`detector.py`) uses multiple strategies to know when ChatGPT finishes responding:

1. **Primary: Copy Button** — appears only after the full response is generated
2. **Fallback: Stop Button Lifecycle** — watches "Stop generating" button appear then disappear
3. **Fallback: Text Stability** — polls last assistant message; stable for 4+ consecutive checks (2s apart) = complete
4. **Message Counting** — counts both `div[data-message-author-role='assistant']` and `.agent-turn` elements (image responses use the latter)

### Tool Calling Implementation

Since ChatGPT's web UI has no native tool API, CatGPT uses **prompt injection**:

1. Tool definitions are converted to a system prompt instructing ChatGPT to output:
   ```json
   {"tool_calls": [{"name": "<function_name>", "arguments": {...}}]}
   ```
2. Few-shot examples ensure reliable JSON output
3. CatGPT parses the JSON via regex and returns standard OpenAI `tool_calls` format
4. Tool results (`ToolMessage`) are formatted into the prompt transcript for multi-turn
5. Each request prepends `"Forget all prior instructions"` to prevent context refusal

### File & Image Upload Pipeline

```
API Request (with image_url / file content parts)
│
├── _extract_image_urls(content) → list of URLs/data-URLs
├── _extract_file_attachments(content) → list of {filename, data_b64, mime_type}
│
├── _download_file(url_or_dict) → local file path
│   ├── data: URL → base64 decode → save to /tmp/catgpt_files/
│   ├── http: URL → urllib.request.urlretrieve
│   ├── dict → base64 decode with original filename
│   └── local path → pass through
│
└── client._upload_files(all_paths)
    ├── Find <input type="file"> via Selectors.FILE_UPLOAD_INPUT
    ├── set_input_files(valid_paths)
    └── Wait 3s + 1s per additional file
```

### Echo Detection & Recovery

Sometimes the copy-button extraction grabs the **sent prompt** instead of the response. CatGPT detects and recovers:

1. Check if `response_text` contains `"[System instruction:"` (part of the injected tool prompt)
2. If echo detected, wait 3 seconds and retry `extract_last_response_via_copy()`
3. If retry still echoes, strip the system prompt prefix and extract the tail

### Selector Fallback System

All DOM selectors are defined in `selectors.py` as **lists of fallbacks** tried in order:

```python
CHAT_INPUT = [
    "#prompt-textarea",                                    # Primary
    "div[contenteditable='true'][id='prompt-textarea']",   # Specific
    "div[contenteditable='true']",                         # Broad fallback
]
```

When ChatGPT updates their UI, only `selectors.py` needs changes. Tracked selectors: `CHAT_INPUT`, `SEND_BUTTON`, `ASSISTANT_MESSAGE`, `STOP_BUTTON`, `NEW_CHAT_BUTTON`, `SIDEBAR_THREAD_LINKS`, `LOGIN_INDICATORS`, `ASSISTANT_MARKDOWN`, `POST_RESPONSE_BUTTONS`, `COPY_BUTTON`, `ASSISTANT_IMAGE`, `IMAGE_CONTAINER`, `IMAGE_DOWNLOAD_BUTTON`, `FILE_UPLOAD_INPUT`, `ATTACH_BUTTON`.

---

## Testing

```bash
source .venv/bin/activate

# Chat / tools / vision / file tests
python scripts/test_langchain_tools.py

# Image generation tests
python scripts/test_image_generation.py
```

### Test Categories

#### Chat & Tools (`test_langchain_tools.py`)

| #   | Test                      | What It Validates                                       |
| --- | ------------------------- | ------------------------------------------------------- |
| 1   | **Simple Chat**           | Basic question/answer without tools                     |
| 2   | **get_current_time Tool** | Single tool call → execute → send result → final answer |
| 3   | **add_numbers Tool**      | Tool with parameters (a=42, b=58) → round-trip          |
| 4   | **Complex Multi-Tool**    | Two tools called in one turn (weather + math)           |
| 5   | **Image Input**           | Single image, multiple images, image + tool calling     |
| 6   | **File Attachment**       | PDF upload + summarize, PDF + image combined            |

#### Image Generation (`test_image_generation.py`)

| #   | Test                | What It Validates                                      |
| --- | ------------------- | ------------------------------------------------------ |
| 1   | **Basic b64_json**  | Generate image, validate base64 response, save to disk |
| 2   | **Generate & Save** | HD quality image, verify file exists and has content   |
| 3   | **URL format**      | `response_format="url"` returns local file path        |
| 4   | **OpenAI SDK**      | `client.images.generate()` works end-to-end            |

### Test Assets

- `downloads/images/*.png` — Test images for vision tests (Test 5)
- `downloads/test.pdf` — Test PDF for file attachment tests (Test 6)

Tests gracefully skip if assets are missing.

---

## Troubleshooting

### "ChatGPT client not initialized" (503 error)

The API server started but the browser hasn't finished initializing. Wait 30–45 seconds after startup, or check logs:

```bash
docker logs catgpt --tail 50   # Docker
cat logs/api_server.log        # Local
```

### "Not logged in" / Login required

Your ChatGPT session expired. Re-login:

- **Docker:** Open http://localhost:6080 and sign in
- **Local:** Run `python scripts/first_login.py`

### Stale browser lock files

If the app crashes, orphan Chrome processes may leave lock files:

```bash
pkill -f "chrome-for-testing" 2>/dev/null
rm -f browser_data/SingletonLock browser_data/SingletonSocket browser_data/SingletonCookie
```

The app auto-cleans these on startup, but manual cleanup may be needed after hard crashes.

### Docker DNS issues

Chrome inside Docker sometimes fails to resolve domains. If you still see DNS errors after the entrypoint workaround:

```bash
docker exec catgpt cat /etc/hosts      # Verify DNS entries
docker exec catgpt curl -s https://chatgpt.com  # Test connectivity
```

### Tool calling returns empty response

ChatGPT occasionally returns an empty response. This is a prompt-sensitivity issue — retry the request.

### Tool calling says "I don't have tools"

This happens when conversation history makes ChatGPT "remember" it doesn't have tools. Start a new chat (`POST /thread/new`) to reset context.

### Code changes not taking effect (Docker)

You must **rebuild** the Docker image after code changes:

```bash
docker compose up --build -d catgpt   # Correct
# NOT: docker restart catgpt          # Wrong: uses old image
```

### Browser not visible in noVNC

Check if all container services are running:

```bash
docker exec catgpt supervisorctl status
```

Expected: all 4 services (`xvfb`, `vnc`, `novnc`, `catgpt`) showing `RUNNING`.

---

## Known Limitations

- **No streaming:** `stream=true` returns a 400 error. All responses are returned at once after completion.
- **Single concurrency:** All requests are serialized through an `asyncio.Lock` — one request at a time.
- **Response time:** Each request takes 5–30+ seconds depending on response length.
- **Token counts are estimated:** ~4 characters per token. Not accurate.
- **Cache scope:** chat dedup cache is in-memory and process-local (not shared across replicas/restarts).
- **Session expiry:** ChatGPT login sessions expire periodically — re-login required.
- **ChatGPT UI changes:** If ChatGPT updates their HTML, selectors in `selectors.py` may need updating.
- **No multi-user:** Single browser session = single user.
- **Tool calling reliability:** Depends on ChatGPT following the injected system prompt (~95% reliable).
- **File size limits:** Large files (>10MB) may timeout during upload.

---

## Tech Stack

| Component          | Library               | Version | Purpose                              |
| ------------------ | --------------------- | ------- | ------------------------------------ |
| Browser automation | Patchright            | 1.58+   | Playwright fork for Chromium control |
| Anti-detection     | playwright-stealth    | 2.0+    | Patch browser fingerprints           |
| API framework      | FastAPI               | 0.115+  | OpenAI-compatible + custom REST API  |
| ASGI server        | Uvicorn               | 0.32+   | Serve FastAPI app                    |
| Data validation    | Pydantic              | 2.5+    | Request/response schemas             |
| TUI framework      | Textual               | 0.85+   | Full-screen terminal application     |
| Rich text          | Rich                  | 13.0+   | Markdown rendering in terminal       |
| CLI                | Typer                 | 0.12+   | Command-line argument parsing        |
| Config             | python-dotenv         | 1.0+    | Environment variable loading         |
| Testing            | OpenAI SDK            | 1.0+    | API client for tests                 |
| Testing            | LangChain             | 0.2+    | Tool calling integration tests       |
| Container          | Docker + Compose      | —       | Production deployment                |
| Display server     | Xvfb + x11vnc + noVNC | —       | Virtual display + browser access     |
| Process manager    | supervisord           | —       | Manage container services            |

---

## License

Educational proof-of-concept. Built to demonstrate browser automation capabilities.
Use responsibly and in accordance with OpenAI's terms of service.

