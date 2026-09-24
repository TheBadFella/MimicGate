# Supported Providers and Configuration

MimicGate Gateway exposes browser-backed and API-backed AI services through OpenAI-compatible, Anthropic Messages, and Ollama APIs. This document lists all supported providers, outlines how to configure each one, summarizes key capabilities, and links to detailed guides across the documentation.

---

## Table of Contents

- [Supported Providers and Configuration](#supported-providers-and-configuration)
  - [Table of Contents](#table-of-contents)
  - [Providers Overview](#providers-overview)
  - [1. ChatGPT (`chatgpt`)](#1-chatgpt-chatgpt)
    - [Configuration](#configuration)
    - [Authentication](#authentication)
    - [Detailed ChatGPT Guides](#detailed-chatgpt-guides)
  - [2. Claude (`claude`)](#2-claude-claude)
    - [Configuration](#configuration-1)
    - [Authentication](#authentication-1)
    - [Detailed Claude Guides](#detailed-claude-guides)
  - [3. Google Gemini (`gemini`)](#3-google-gemini-gemini)
    - [Configuration](#configuration-2)
    - [Supported Models](#supported-models)
    - [Authentication](#authentication-2)
    - [Detailed Gemini Guides](#detailed-gemini-guides)
  - [4. MiniMax (`minimax`)](#4-minimax-minimax)
    - [Configuration](#configuration-3)
    - [Authentication](#authentication-3)
    - [Detailed MiniMax Guides](#detailed-minimax-guides)
  - [Switching Between Providers](#switching-between-providers)
  - [Provider Capabilities Comparison](#provider-capabilities-comparison)
  - [Related Documentation](#related-documentation)

---

## Providers Overview

| Provider | Type | Default Model | Login / Auth Method | Notable Capabilities |
|---|---|---|---|---|
| **ChatGPT** | Persistent browser | `mimicgate-browser` | Browser login (email/pass, Apple, MS, OTP) | Vision, files, DALL-E image generation, read-aloud TTS, model/effort picker |
| **Claude** | Persistent browser | `claude-browser` | Browser login (email OTP, password, Apple) | Vision, files, tool calling, Anthropic Messages adapter |
| **Google Gemini** | Persistent browser | `gemini-browser` | Browser login (Google Account direct) | Vision, files, Imagen 3 image generation, Listen TTS audio, reasoning effort, model switcher |
| **MiniMax** | Official API | `MiniMax-M2.7` | API Key (`MINIMAX_API_KEY`) | Fast text completions, zero browser overhead, no graphical display required |

---

## 1. ChatGPT (`chatgpt`)

ChatGPT uses a persistent, automated Chromium browser running against `https://chatgpt.com`.

### Configuration

Set the following variables in your `.env` file or Docker Compose environment:

```dotenv
PROVIDER=chatgpt
BROWSER_DATA_DIR=./browser_data
CHATGPT_URL=https://chatgpt.com
CHATGPT_DEFAULT_MODEL=
CHATGPT_PROJECT_URL=
CHATGPT_LONG_PROMPT_FALLBACK=attachment
```

Key configuration options:
- `PROVIDER`: Set to `chatgpt` (the default).
- `BROWSER_DATA_DIR`: Directory where session cookies and tokens are persisted (default: `browser_data`).
- `CHATGPT_DEFAULT_MODEL`: Default model mapping when requests specify `mimicgate-browser` or omit a model.
- `CHATGPT_PROJECT_URL`: Optional project URL (e.g. `https://chatgpt.com/g/g-p-.../project`) to restrict conversations to a workspace project.
- `CHATGPT_MODEL_ALIASES` & `CHATGPT_MODEL_SETTINGS`: Custom model labels and effort levels.
- `CHATGPT_LONG_PROMPT_FALLBACK`: Uploads oversized requests as text attachments when the composer limit is exceeded.

### Authentication

Sign in once via the jlesage web GUI at `http://localhost:5800` (Docker) or by running `python scripts/first_login.py` (local).

> [!IMPORTANT]
> Use email + password, Microsoft account, Apple ID, or magic link / OTP email. Third-party "Continue with Google" OAuth buttons are blocked by Google bot detection in automated browsers.

### Detailed ChatGPT Guides

- [Installation & Setup Guide](INSTALLATION_AND_SETUP.md): Initial browser login and Docker instructions.
- [Model & Reasoning Selection Guide](MODEL_AND_REASONING_SELECTION.md): Advanced model picker and effort controls.
- [API Reference](API_REFERENCE.md): Request formatting, image generation, and read-aloud audio capture.
- [Environment Variables](ENVIRONMENT_VARIABLES.md): Full reference of all ChatGPT variables.

---

## 2. Claude (`claude`)

Claude uses persistent browser automation connecting to `https://claude.ai`.

### Configuration

Set the following variables in `.env`:

```dotenv
PROVIDER=claude
BROWSER_DATA_DIR=./browser_data_claude
CLAUDE_URL=https://claude.ai
```

Key configuration options:
- `PROVIDER`: Set to `claude`.
- `BROWSER_DATA_DIR`: Directory for Claude session cookies and browser profiles (default: `browser_data_claude`).
- `CLAUDE_URL`: Claude web target (default: `https://claude.ai`).

### Authentication

Open `http://localhost:5800` (Docker) or run `python scripts/first_login.py` (local) with `PROVIDER=claude`. Sign in using email OTP, password, or Apple ID. Once you reach the Claude chat interface, the profile is saved automatically.

### Detailed Claude Guides

- [Installation & Setup Guide](INSTALLATION_AND_SETUP.md): First-time login and Docker instructions.
- [API Reference](API_REFERENCE.md): OpenAI completions and Anthropic Messages adapter endpoints.
- [Environment Variables](ENVIRONMENT_VARIABLES.md): Environment settings for Claude.

---

## 3. Google Gemini (`gemini`)

Google Gemini connects through persistent browser automation interacting with `https://gemini.google.com`.

### Configuration

Set the following variables in `.env`:

```dotenv
PROVIDER=gemini
BROWSER_DATA_DIR=./browser_data_gemini
GEMINI_URL=https://gemini.google.com
GEMINI_DEFAULT_MODEL=gemini-browser
GEMINI_MODEL_FALLBACK=true
GEMINI_LONG_PROMPT_FALLBACK=attachment
```

Key configuration options:
- `PROVIDER`: Set to `gemini`.
- `BROWSER_DATA_DIR`: Directory for Gemini session cookies (default: `browser_data_gemini`).
- `GEMINI_DEFAULT_MODEL`: Default model when not specified (default: `gemini-browser`, which preserves active UI selection).
- `GEMINI_MODEL_FALLBACK`: Falls back to default model on unknown model IDs (`true`) or rejects with HTTP 400 (`false`).
- `GEMINI_MODEL_ALIASES`: Custom mappings between API model IDs and Gemini dropdown menu labels.
- `GEMINI_LONG_PROMPT_FALLBACK`: Uploads long prompts as attachments when input limits are reached.

### Supported Models

- `gemini-browser`: Preserves whichever model is currently active in the UI.
- `gemini-3.8-flash`: Default high-speed multimodal model.
- `gemini-3.6-flash`: Previous generation Flash model.
- `gemini-3.5-flash-lite`: Ultra-low latency model.
- `gemini-3.1-pro`: Advanced reasoning model (requires Google One AI Premium / Gemini Advanced).
- `gemini-extended-thinking`: Deep reasoning with visible thinking process.

### Authentication

Unlike third-party sites where Google OAuth popups are restricted, signing directly into your Google Account on `gemini.google.com` works normally. Sign in via `http://localhost:5800` (Docker) or `python scripts/first_login.py` (local) and complete two-factor authentication if prompted.

### Detailed Gemini Guides

- [Gemini Provider Guide](GEMINI_PROVIDER_GUIDE.md): Dedicated walkthrough for setup, models, TTS, and images.
- [Model & Reasoning Selection Guide](MODEL_AND_REASONING_SELECTION.md): Mode switcher interaction and reasoning effort tokens.
- [API Reference](API_REFERENCE.md): Multimodal vision, file attachments, and Listen TTS capture.
- [Environment Variables](ENVIRONMENT_VARIABLES.md): Environment settings for Gemini.

---

## 4. MiniMax (`minimax`)

MiniMax connects directly to MiniMax's official API, providing fast OpenAI-compatible chat completions without running a browser instance.

### Configuration

Set the following variables in `.env`:

```dotenv
PROVIDER=minimax
MINIMAX_API_KEY=your-minimax-api-key
MINIMAX_REGION=global_en
MINIMAX_MODEL=MiniMax-M2.7
```

Key configuration options:
- `PROVIDER`: Set to `minimax`.
- `MINIMAX_API_KEY`: Your MiniMax API key (required).
- `MINIMAX_REGION`: `global_en` (`https://api.minimax.io/v1`) or `cn_zh` (`https://api.minimaxi.com/v1`).
- `MINIMAX_BASE_URL`: Optional custom base URL override.
- `MINIMAX_MODEL`: Exposed model identifier (default: `MiniMax-M2.7`).

### Authentication

MiniMax uses standard API keys. Obtain an API key from the MiniMax developer platform and configure `MINIMAX_API_KEY`. No interactive browser login or display server is needed.

### Detailed MiniMax Guides

- [API Reference](API_REFERENCE.md): Request format and completions handling.
- [Environment Variables](ENVIRONMENT_VARIABLES.md): Region and endpoint options.

---

## Switching Between Providers

Each browser provider maintains its own isolated profile directory:
- `browser_data/` for ChatGPT
- `browser_data_claude/` for Claude
- `browser_data_gemini/` for Gemini

To switch providers:

1. Update `PROVIDER` and `BROWSER_DATA_DIR` in your `.env` file:
   ```bash
   # Switch to Gemini
   PROVIDER=gemini
   BROWSER_DATA_DIR=./browser_data_gemini
   ```
2. For Docker, ensure `PROVIDER` is updated in `docker-compose.yml` under `services.mimicgate.environment`, then restart:
   ```bash
   docker compose up --build -d
   ```
3. Complete the one-time login for the new provider if you have not logged into it previously.

---

## Provider Capabilities Comparison

| Capability | ChatGPT | Claude | Gemini | MiniMax |
|---|:---:|:---:|:---:|:---:|
| **Browser Required** | Yes | Yes | Yes | No |
| **OpenAI Chat Completions** | Yes | Yes | Yes | Yes |
| **OpenAI Responses API** | Yes | Yes | Yes | No |
| **Anthropic `/v1/messages`** | Yes | Yes | Yes | No |
| **Ollama `/api/chat`** | Yes | Yes | Yes | Yes |
| **Tool / Function Calling** | Yes | Yes | Yes | No |
| **Vision Input (Images)** | Yes | Yes | Yes | No |
| **File Attachments** | Yes | Yes | Yes | No |
| **Image Generation** | Yes (DALL-E) | No (501) | Yes (Imagen 3) | No |
| **Text-to-Speech (Audio)** | Yes (`read_aloud`) | No | Yes (`read_aloud`) | No |
| **Model / Effort Switching** | Yes | No | Yes | No |
| **Long-Prompt Fallback** | Attachment upload | No | Attachment upload | No |

---

## Related Documentation

- [Documentation Index](README.md): Comprehensive navigation of all repository guides.
- [Installation & Setup Guide](INSTALLATION_AND_SETUP.md): Step-by-step setup for Docker, local, and Nix.
- [Gemini Provider Guide](GEMINI_PROVIDER_GUIDE.md): Deep dive into Gemini configuration.
- [Model & Reasoning Selection Guide](MODEL_AND_REASONING_SELECTION.md): Model selection and reasoning effort levels.
- [API Reference](API_REFERENCE.md): Complete endpoint and parameter specifications.
- [Environment Variables Reference](ENVIRONMENT_VARIABLES.md): Every supported setting and default.
- [System Architecture](SYSTEM_ARCHITECTURE.md): Multi-tab routing, session pools, and browser management.

