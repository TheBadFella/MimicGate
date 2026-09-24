<p align="center">
  <img src="assets/mimicgate_header.png" width="180" alt="MimicGate logo" />
</p>

<h1 align="center">MimicGate</h1>

<p align="center">
  <strong>A browser-backed, multi-protocol AI gateway for ChatGPT, Claude, Gemini, and MiniMax.</strong><br />
  Connect OpenAI, Anthropic, Ollama, LangChain, Cline, and self-hosted clients to one persistent gateway.
</p>

<p align="center">
  <a href="https://github.com/TheBadFella/MimicGate/releases/latest"><img src="https://img.shields.io/github/v/release/TheBadFella/MimicGate?style=for-the-badge&color=1976D2" alt="Latest release" /></a>
  <a href="https://github.com/TheBadFella/MimicGate/pkgs/container/mimicgate"><img src="https://img.shields.io/badge/GHCR-ready-00897B?style=for-the-badge&logo=docker&logoColor=white" alt="GHCR image" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/TheBadFella/MimicGate?style=for-the-badge&color=F9A825" alt="MIT license" /></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> ·
  <a href="#why-this-fork">Features</a> ·
  <a href="#fork-vs-upstream">Fork vs Upstream</a> ·
  <a href="docs/README.md">Documentation</a> ·
  <a href="docs/PROVIDERS.md">Providers</a> ·
  <a href="docs/API_REFERENCE.md">API</a> ·
  <a href="docs/ENVIRONMENT_VARIABLES.md">Environment</a> ·
  <a href="docs/INSTALLATION_AND_SETUP.md">Setup</a> ·
  <a href="docs/GEMINI_PROVIDER_GUIDE.md">Gemini</a> ·
  <a href="docs/SYSTEM_ARCHITECTURE.md">Architecture</a>
</p>

---

MimicGate turns a logged-in browser session into familiar API endpoints. ChatGPT, Claude, and Gemini use a persistent, automated browser; MiniMax uses its official API while keeping the same gateway interface. It is designed for private, self-hosted integrations, not as an official provider API.

## Why This Fork

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>🔌 Protocol Compatibility</h3>
      OpenAI Chat Completions and Responses, Anthropic Messages, Ollama chat/generate/embed, tool calling, and SSE-compatible responses for IDE clients such as Cline and OpenCode.
    </td>
    <td width="50%" valign="top">
      <h3>⚡ Sessions & Scale</h3>
      Multi-tab concurrency, persistent <code>x-session-id</code> sessions, explicit thread targeting, async jobs, and app-scoped conversation isolation.
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3>🖼️ Documents & Media</h3>
      Vision, file attachments, multipage extraction, JSON Schema output, ChatGPT image generation, and read-aloud audio capture.
    </td>
    <td width="50%" valign="top">
      <h3>🛡️ Resilience & Operations</h3>
      Long-prompt attachment fallback, configurable model effort, robust response detection, optional auth, health checks, and a non-root jlesage GUI.
    </td>
  </tr>
</table>

> [!TIP]
> Long-prompt fallback is enabled by default. If ChatGPT disables direct submission, MimicGate uploads the complete request as a temporary UTF-8 attachment. The flow has been validated with a 1.4-million-character request.

## Fork vs Upstream

Both projects share the core browser gateway: ChatGPT and Claude support, OpenAI Chat Completions, tool calling, vision and file inputs, image generation, multi-tab concurrency, persistent sessions, SSE compatibility, a terminal client, and Docker deployment.

This table focuses only on meaningful differences:

| Capability | This fork | Upstream |
|---|:---:|:---:|
| Google Gemini browser provider | ✅ | — |
| OpenAI Responses API | ✅ | — |
| Anthropic Messages adapter | ✅ | — |
| Ollama-compatible API | ✅ | — |
| MiniMax provider | ✅ | — |
| Async completion jobs | ✅ | — |
| App-scoped routes and thread isolation | ✅ | — |
| Explicit ChatGPT thread targeting | ✅ | Basic REST only |
| JSON Schema normalization | ✅ | — |
| Structured multipage extraction | ✅ | — |
| ChatGPT read-aloud audio capture | ✅ | — |
| Long-prompt attachment fallback | ✅ | — |
| Configurable model and effort routing | ✅ | — |
| Non-root jlesage browser GUI | ✅ | — |
| Live multi-tab preview dashboard | — | ✅ |

<sub>Comparison verified against <a href="https://github.com/GautamVhavle/CatGPT-Gateway">upstream</a> at commit <code>1771f5b</code>.</sub>

## Providers

| Provider | Connection | Model | Notable capabilities |
|---|---|---|---|
| ChatGPT | Persistent browser | `mimicgate-browser` or configured GPT model | Images, vision, files, audio, model/effort switching |
| Claude | Persistent browser | `claude-browser` | Chat, vision, files, tools |
| Gemini | Persistent browser | `gemini-browser` or configured Gemini model | Chat, vision, files, image generation, audio/TTS, reasoning effort, model switching |
| MiniMax | Official API | `MiniMax-M2.7` | OpenAI-compatible text requests without a browser |

## Backwards Compatibility

MimicGate is a rename of the CatGPT project. Existing integrations keep working:

- The legacy `catgpt-browser` model ID is still accepted and behaves exactly like `mimicgate-browser`.
- The `x-catgpt-app-key`, `x-catgpt-conversation-id`, and `x-catgpt-thread-mode` headers remain supported; `x-mimicgate-*` takes precedence when both are present.
- The `catgpt` console script and the `CatGPTApp` import remain available as aliases.
- The `CATGPT_API_URL`, `CATGPT_API_KEY`, `CATGPT_MODEL`, and Compose `CATGPT_*` variables are still read as fallbacks.

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/TheBadFella/MimicGate.git
cd MimicGate
```

Create `.env` with your own credentials (the checked-in defaults are intentionally only suitable for local testing):

```dotenv
MIMICGATE_API_KEY=replace-me
MIMICGATE_VNC_PASSWORD=replace-me
MIMICGATE_USER_ID=1000
MIMICGATE_GROUP_ID=1000
```

See the [generated environment reference](docs/ENVIRONMENT_VARIABLES.md) for every setting and its default.

### 2. Start the container

```bash
docker compose up -d
```

| Service | Address |
|---|---|
| Browser login and recovery | `http://localhost:5800` |
| API gateway | `http://localhost:8650` |

Open the browser GUI, enter the VNC password, and sign in to the selected browser provider once. The profile persists across restarts.

### 3. Send a request

```bash
curl http://localhost:8650/v1/chat/completions \
  -H "Authorization: Bearer $MIMICGATE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mimicgate-browser",
    "messages": [{"role": "user", "content": "Say hello from MimicGate."}]
  }'
```

## API Surfaces

| Client ecosystem | Primary endpoints |
|---|---|
| OpenAI | `/v1/chat/completions`, `/v1/responses`, `/v1/images/generations`, `/v1/models` |
| Anthropic | `/v1/messages` |
| Ollama | `/api/chat`, `/api/generate`, `/api/embed`, `/api/tags` |
| Cline / OpenCode | `/cline/v1/chat/completions` (OpenAI-compatible; SSE `stream=true`) |
| Native MimicGate | `/chat`, `/thread/{id}/chat`, `/thread/new`, `/threads`, `/status` |

Use `/{app_name}/v1/...` or `/{app_name}/api/...` routes to isolate applications such as Cline, Open WebUI, Mealie, Linkwarden, or internal agents. Use `conversation_id` (or `X-MimicGate-Conversation-Id`) for durable, history-verified continuity; `thread_id` and `x-session-id` remain available for direct browser-thread and tab affinity. Send `X-MimicGate-Thread-Mode: fresh` when a request must start an isolated ephemeral thread. The legacy `X-CatGPT-*` headers are still accepted.

In Cline, choose **OpenAI Compatible**, set Base URL to `http://localhost:8650/cline/v1`, API Key to `MIMICGATE_API_KEY`, and Model ID to `mimicgate-browser` (or `claude-browser` / `gemini-browser`).

> [!NOTE]
> `stream=true` is protocol-compatible, but browser generation finishes before MimicGate emits the SSE or NDJSON response chunks. It is not live token forwarding from the provider.

## Essential Configuration

| Variable | Default | Purpose |
|---|---|---|
| `PROVIDER` | `chatgpt` | Select `chatgpt`, `claude`, `gemini`, or `minimax` |
| `MIMICGATE_API_KEY` | `dummy123` | Bearer token used by Docker Compose |
| `MIMICGATE_VNC_PASSWORD` | `mimicgate` | Browser GUI password |
| `MAX_CONCURRENT_REQUESTS` | `3` | Concurrent browser-backed requests |
| `CHATGPT_DEFAULT_MODEL` | Current UI selection | Default ChatGPT model mapping |
| `GEMINI_DEFAULT_MODEL` | `gemini-browser` | Default Gemini model mapping |
| `CHATGPT_PROJECT_URL` | Empty | Confine ChatGPT threads to one project |
| `CHATGPT_LONG_PROMPT_FALLBACK` | `attachment` | Upload oversized prompts or use `error` for HTTP 413 |

See the [generated environment reference](docs/ENVIRONMENT_VARIABLES.md), [docker-compose.yml](docker-compose.yml), and the [Installation & Setup Guide](docs/INSTALLATION_AND_SETUP.md) for advanced options. Add runtime-only Docker overrides under `services.mimicgate.environment`.

## Documentation

Explore the full [MimicGate Documentation Index](docs/README.md) or browse directly:

| Guide | What it covers |
|---|---|
| [Supported Providers](docs/PROVIDERS.md) | Comprehensive overview of supported providers (ChatGPT, Claude, Gemini, MiniMax) and setup |
| [Installation & Setup](docs/INSTALLATION_AND_SETUP.md) | Docker, local installation, login, persistence, and troubleshooting |
| [Gemini Provider Guide](docs/GEMINI_PROVIDER_GUIDE.md) | Dedicated Gemini configuration, login, model list, and TTS/image options |
| [API Reference](docs/API_REFERENCE.md) | Request formats, tools, vision, files, images, audio, and native routes |
| [Environment Variables](docs/ENVIRONMENT_VARIABLES.md) | Every runtime and Docker Compose variable, default, and purpose |
| [Model & Reasoning Selection](docs/MODEL_AND_REASONING_SELECTION.md) | ChatGPT and Gemini model aliases, versions, and effort settings |
| [System Architecture](docs/SYSTEM_ARCHITECTURE.md) | Browser lifecycle, routing, extraction, and response detection |
| [Browser Automation Runbook](docs/BROWSER_AUTOMATION_RUNBOOK.md) | Browser automation diagnostics and recovery |
| [Testing & Verification](docs/TESTING_AND_VERIFICATION.md) | Reproducible unit, environment, container, and browser smoke checks |

## Operational Notes

- Browser-backed requests take as long as the provider UI takes to answer.
- Provider UI updates can require selector or detector maintenance.
- Keep browser data, logs, and jlesage configuration on persistent volumes.
- Pull a new image with `docker compose pull && docker compose up -d`.

## Credits & License

MimicGate is a feature-focused fork of [GautamVhavle/CatGPT-Gateway](https://github.com/GautamVhavle/CatGPT-Gateway). Contributions and upstream improvements are credited through the shared Git history.

Released under the [MIT License](LICENSE).
