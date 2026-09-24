# Google Gemini Setup Guide

MimicGate Gateway supports Google Gemini (`https://gemini.google.com`) through persistent browser automation. This allows OpenAI-compatible clients, Anthropic Messages clients, Ollama clients, and IDE extensions like Cline to interact with Gemini through standard APIs.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Authentication and First Login](#authentication-and-first-login)
- [Available Models](#available-models)
- [Adding New Gemini Models](#adding-new-gemini-models)
- [Reasoning Effort](#reasoning-effort)
- [Configuration Reference](#configuration-reference)
- [Features and Examples](#features-and-examples)
  - [Chat Completions](#chat-completions)
  - [Image Generation](#image-generation)
  - [Text-to-Speech (Read Aloud)](#text-to-speech-read-aloud)
  - [IDE Clients (Cline)](#ide-clients-cline)
- [Related Documentation](#related-documentation)

---

## Quick Start

### Docker Setup

1. In your `.env` file (or `docker-compose.yml`), set the provider to Gemini:

```dotenv
PROVIDER=gemini
MIMICGATE_API_KEY=your-api-key
MIMICGATE_VNC_PASSWORD=your-vnc-password
```

2. Start the container:

```bash
docker compose up --build -d
```

3. Open `http://localhost:5800` in your web browser, enter your VNC password, and log in to your Google Account.
4. Once you see the Gemini chat screen (`gemini.google.com/app`), close the web GUI tab.
5. Send a test request:

```bash
curl http://localhost:8650/v1/chat/completions \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-browser",
    "messages": [{"role": "user", "content": "Hello from MimicGate!"}]
  }'
```

### Local Setup (Without Docker)

1. Set environment variables in your `.env` file:

```dotenv
PROVIDER=gemini
BROWSER_DATA_DIR=./browser_data_gemini
API_TOKEN=dummy123
```

2. Perform the one-time interactive login:

```bash
python scripts/first_login.py
```

3. Sign in to your Google Account in the opened Chromium window and press Enter in the terminal once the chat screen appears.
4. Start the API server:

```bash
python -m src.api.server
```

---

## Authentication and First Login

MimicGate Gateway uses a persistent browser profile. You only need to log in once, and your session tokens and cookies will be preserved across restarts.

> [!NOTE]
> Third-party "Sign in with Google" OAuth buttons are often blocked by Google bot detection when logging into external services like ChatGPT or Claude. However, when using the Gemini provider, you are signing directly into your Google Account on `gemini.google.com`, which works normally.

### Docker Login Flow

1. Navigate to the jlesage browser interface at `http://localhost:5800`.
2. Sign into your Google Account using your email and password.
3. Complete any two-factor verification prompts (such as Google Authenticator, SMS, or phone prompts).
4. Wait until the Gemini conversation page loads with the prompt input box visible.
5. Close the browser GUI tab. The profile is saved in `${DOCKERDIR}/appdata/mimicgate/browser` on the host.

### Local Login Flow

1. Run `python scripts/first_login.py`.
2. Chromium will open to `https://gemini.google.com/app`.
3. Sign into your Google Account and complete any two-factor authentication.
4. When the Gemini chat interface appears, return to the terminal and press Enter.
5. The session is saved to `./browser_data_gemini`.

---

## Available Models

MimicGate interacts directly with Gemini's model switcher (`<bard-mode-switcher>`) to select the requested model before submitting prompts.

| Public Model ID | UI Menu Label | Description |
|---|---|---|
| `gemini-browser` | *(Active UI selection)* | Preserves whichever model is currently selected in the browser UI (default). |
| `gemini-3.8-flash` | `3.8 Flash` / `Flash` | Default high-speed multimodal model. |
| `gemini-3.6-flash` | `3.6 Flash` | Previous generation Flash model. |
| `gemini-3.5-flash-lite` | `3.5 Flash-Lite` | Ultra-low latency lightweight model. |
| `gemini-3.1-pro` | `3.1 Pro` / `Advanced` | Advanced reasoning model (requires Google One AI Premium / Gemini Advanced). |
| `gemini-extended-thinking` | `Extended thinking` | Deep reasoning with visible chain-of-thought. |

### Model Aliases

The following aliases are pre-configured:

- `gemini-flash`, `gemini-2.0-flash`, `gemini-1.5-flash` map to Flash (`gemini-3.8-flash`).
- `gemini-pro`, `gemini-1.5-pro` map to `3.1 Pro` (`gemini-3.1-pro`).

### Auto-Model Fallbacks

To ensure smooth compatibility with clients configured for other providers, the following model IDs automatically resolve to the active browser model (`gemini-browser`):

- `mimicgate-browser`, `claude-browser`
- `auto`, `default`, `browser`, `gemini`
- `gpt-4o`, `gpt-4o-mini`, `gpt-4`, `gpt-3.5-turbo`

---

## Adding New Gemini Models

Google frequently updates its Gemini model lineup and UI labels.

When Google releases a new model or changes UI labels in the Gemini interface, the model needs to be added to the code in `src/gemini/model_registry.py` under `DEFAULT_GEMINI_MODELS`.

### How Users Can Request Support for New Models

If you notice a new model in Gemini that is not yet recognized by MimicGate:

1. Open a GitHub Issue at [https://github.com/TheBadFella/MimicGate/issues](https://github.com/TheBadFella/MimicGate/issues).
2. Provide the following information:
   - The model name displayed in the Gemini web interface.
   - The exact text label shown in the Gemini model switcher dropdown menu.
   - Any sub-options or reasoning tiers associated with the model.
   - Your account tier (Free or Gemini Advanced / Google One AI Premium).

### Temporary Custom Model Mapping

Before a release adds the model to the codebase, you can map it immediately using the `GEMINI_MODEL_ALIASES` environment variable:

```dotenv
GEMINI_MODEL_ALIASES="gemini-next-model=Next Model Label|Alternate Label"
```

Format: `public_id=Primary Label|Alternate Label 1|Alternate Label 2`. Multiple definitions can be separated by commas.

---

## Reasoning Effort

Gemini supports reasoning effort mapping via the `reasoning_effort` parameter in Chat Completions or Responses requests.

- **High reasoning levels** (`high`, `xhigh`, `extended`, `max`, `ultra`, `thinking`, `deep`, `complex`):
  Automatically select `gemini-extended-thinking`.
- **Low / disabled reasoning levels** (`none`, `minimal`, `low`, `off`, `disabled`, `min`):
  Downgrade reasoning models to standard `gemini-3.1-pro` or `gemini-3.8-flash`.

Example:

```bash
curl http://localhost:8650/v1/chat/completions \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-browser",
    "reasoning_effort": "high",
    "messages": [{"role": "user", "content": "Solve this logic puzzle step by step..."}]
  }'
```

---

## Configuration Reference

The following environment variables control Gemini provider behavior:

| Variable | Default | Purpose |
|---|---|---|
| `PROVIDER` | `chatgpt` | Set to `gemini` to activate the Gemini provider. |
| `GEMINI_URL` | `https://gemini.google.com` | Base URL for Gemini web interface. |
| `GEMINI_DEFAULT_MODEL` | `gemini-browser` | Model to use when none is specified or when `gemini-browser` is requested. |
| `GEMINI_MODEL_FALLBACK` | `true` | When `true`, unrecognized model IDs fall back to `GEMINI_DEFAULT_MODEL`. When `false`, returns HTTP 400. |
| `GEMINI_MODEL_ALIASES` | *(Pre-configured defaults)* | Comma-separated list mapping custom API model IDs to visible UI labels. |
| `GEMINI_MODEL_DISCOVERY_TTL_SECONDS` | `3600` | How long to cache dynamically discovered model options from the UI. |
| `GEMINI_LONG_PROMPT_FALLBACK` | `attachment` | Fallback method when prompts exceed UI limits (`attachment` or `error`). |
| `GEMINI_LONG_PROMPT_THRESHOLD` | `0` | Character threshold for attachment fallback (`0` = auto-detected). |

See [docs/ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) for the complete list of gateway environment variables.

---

## Features and Examples

### Chat Completions

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8650/v1", api_key="dummy123")

response = client.chat.completions.create(
    model="gemini-3.8-flash",
    messages=[
        {"role": "system", "content": "You are a concise assistant."},
        {"role": "user", "content": "Explain quantum computing in one sentence."}
    ]
)
print(response.choices[0].message.content)
```

### Image Generation

MimicGate routes image generation requests directly through Gemini (Imagen 3):

```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8650/v1", api_key="dummy123")

result = client.images.generate(
    prompt="A futuristic solar-powered cat lounging on a mossy balcony in neo-Tokyo",
    n=1,
    size="1024x1024"
)
print("Image URL:", result.data[0].url)
```

Images can also be requested via the standard `POST /v1/images/generations` HTTP endpoint.

### Text-to-Speech (Read Aloud)

MimicGate supports Gemini's native read-aloud functionality. When `read_aloud: true` is included in the request body, MimicGate triggers Gemini's TTS audio, captures the audio stream, saves it to the downloads directory, and returns the audio metadata in the response:

```bash
curl http://localhost:8650/v1/chat/completions \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-browser",
    "messages": [{"role": "user", "content": "Say hello in three words."}],
    "read_aloud": true
  }'
```

### IDE Clients (Cline)

To use Gemini with Cline or OpenCode:

1. Set the API provider to **OpenAI Compatible**.
2. Base URL: `http://localhost:8650/cline/v1`
3. API Key: your `MIMICGATE_API_KEY` (e.g. `dummy123`).
4. Model ID: `gemini-browser` or `gemini-3.8-flash`.

MimicGate maintains conversation continuity and tab affinity for Cline requests automatically.

---

## Related Documentation

- [Documentation Index](README.md): Overview of all MimicGate Gateway guides and manuals.
- [Installation & Setup Guide](INSTALLATION_AND_SETUP.md): Docker, local installation, and operational guidance.
- [Environment Variables](ENVIRONMENT_VARIABLES.md): Full reference of all configuration options.
- [Model & Reasoning Selection Guide](MODEL_AND_REASONING_SELECTION.md): Model selector details across providers.
- [API Reference](API_REFERENCE.md): Endpoint specifications, tools, and multimodal input formats.
- [System Architecture Guide](SYSTEM_ARCHITECTURE.md): Browser lifecycle and multi-tab routing design.

