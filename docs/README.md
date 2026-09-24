# MimicGate Gateway Documentation

Welcome to the MimicGate Gateway documentation. This directory contains detailed architectural guides, API references, provider configuration instructions, operational runbooks, and testing procedures.

> [!NOTE]
> MimicGate was previously named CatGPT. The legacy `catgpt-browser` model ID, the `x-catgpt-*` request headers, the `catgpt` console script, the `CatGPTApp` import, and the `CATGPT_*` environment variables are all still supported.

---

## Documentation Index

| Document | Category | What it covers |
|---|---|---|
| [INSTALLATION_AND_SETUP.md](INSTALLATION_AND_SETUP.md) | Setup & Deployment | Docker Compose setup, local Python installation, Nix flake, first-time interactive login, and troubleshooting. |
| [PROVIDERS.md](PROVIDERS.md) | Providers & Setup | Full list of supported providers (ChatGPT, Claude, Gemini, MiniMax), configuration, and capabilities comparison. |
| [GEMINI_PROVIDER_GUIDE.md](GEMINI_PROVIDER_GUIDE.md) | Provider Guide | Dedicated Google Gemini setup, direct Google Account login, model catalog, Imagen 3 image generation, and Listen TTS capture. |
| [API_REFERENCE.md](API_REFERENCE.md) | API & Protocols | OpenAI-compatible endpoints, Responses API, Anthropic Messages adapter, Ollama endpoints, native REST routes, and provider differences. |
| [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) | Configuration | Complete reference of every runtime environment variable, Docker Compose setting, default value, and operational purpose. |
| [MODEL_AND_REASONING_SELECTION.md](MODEL_AND_REASONING_SELECTION.md) | Model Configuration | Model switching, picker automation, custom model aliases, and reasoning effort levels across ChatGPT and Gemini. |
| [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) | Architecture | Gateway internals, browser tab pooling, session lifecycle, conversation isolation, persistence, and response detection. |
| [BROWSER_AUTOMATION_RUNBOOK.md](BROWSER_AUTOMATION_RUNBOOK.md) | Operations | Patchright/Chromium troubleshooting, CDP remote debugging, lock file cleanup, and browser recovery procedures. |
| [TESTING_AND_VERIFICATION.md](TESTING_AND_VERIFICATION.md) | Quality & Testing | Unit test suite execution, integration checks, environment verification, and live browser smoke test scripts. |

---

## Document Details

### Getting Started and Deployment

- **[INSTALLATION_AND_SETUP.md](INSTALLATION_AND_SETUP.md)**
  - Prerequisites and system requirements.
  - Recommended Docker deployment with jlesage browser web GUI (`http://localhost:5800`).
  - Local Python virtual environment installation and Chromium setup via Patchright.
  - Nix flake environment instructions.
  - First-time login instructions and persistent browser profile handling.
  - Provider switching instructions and browser directory isolation (`browser_data`, `browser_data_claude`, `browser_data_gemini`).
  - Container internals, volume mounts, systemd service configuration, and troubleshooting.

- **[PROVIDERS.md](PROVIDERS.md)**
  - Summary of all four supported providers: ChatGPT, Claude, Google Gemini, and MiniMax.
  - Configuration parameters, credentials, and environment settings for each provider.
  - Authentication options and browser directory requirements.
  - Side-by-side feature comparison table across protocols, vision, tools, media, and latency.
  - Direct links to dedicated setup guides, API reference, and environment settings.

- **[GEMINI_PROVIDER_GUIDE.md](GEMINI_PROVIDER_GUIDE.md)**
  - Dedicated configuration guide for `PROVIDER=gemini`.
  - Explains direct Google Account authentication on `gemini.google.com`.
  - Complete list of supported Gemini models (`gemini-browser`, `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-pro`, `gemini-extended-thinking`).
  - Dynamic model discovery and custom model aliases via `GEMINI_MODEL_ALIASES`.
  - How to report and request new Gemini models via GitHub issues when Google releases updates.
  - Reasoning effort mapping from OpenAI-compatible parameters.
  - Feature walkthroughs: multimodal vision, file uploads, Imagen 3 image generation, and read-aloud TTS audio.
  - IDE integration instructions for Cline and OpenCode.

### Configuration and Models

- **[ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)**
  - Auto-generated, verified reference of all environment variables supported by MimicGate Gateway.
  - Grouped by functional category: Provider & Browser, Server & Security, Concurrency & Sessions, ChatGPT Settings, Gemini Settings, MiniMax Settings, and Long-Prompt Fallback.
  - Maintained automatically via `python scripts/generate_env_reference.py`.

- **[MODEL_AND_REASONING_SELECTION.md](MODEL_AND_REASONING_SELECTION.md)**
  - Explains how MimicGate interacts with provider model switchers before prompt dispatch.
  - ChatGPT model selector: configuring `CHATGPT_MODEL_ALIASES`, `CHATGPT_MODEL_SETTINGS`, effort menus (Instant, Medium, High, Extra High, Pro), and strict switching mode.
  - Gemini model selector: `<bard-mode-switcher>` automation, `GEMINI_DEFAULT_MODEL`, `GEMINI_MODEL_FALLBACK`, and model resolution logic.

### API Reference and Architecture

- **[API_REFERENCE.md](API_REFERENCE.md)**
  - Base URLs, authentication headers (`Bearer token`), and security configuration.
  - Standard OpenAI-compatible endpoints: `/v1/chat/completions`, `/v1/responses`, `/v1/images/generations`, `/v1/models`.
  - Tool and function calling formats, tool choice handling, and retry mechanics.
  - Vision inputs (base64 data and image URLs) and file attachment handling.
  - Streaming compatibility (pseudo-SSE event stream forwarding).
  - Native MimicGate REST endpoints (`/chat`, `/thread/new`, `/thread/{id}/chat`, `/threads`, `/status`).
  - Terminal chat client (TUI) commands.
  - Comprehensive provider capability comparison table across Claude, ChatGPT, and Gemini.

- **[SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)**
  - High-level system architecture and component interactions.
  - Browser lifecycle management and persistent browser profile handling.
  - Multi-tab browser page pooling and session-affinity serialization.
  - Durable conversation identity tracking and history prefix verification (`conversation_id`).
  - Response detection pipeline: turn tracking, thinking state detection, completion settling, and media extraction.
  - Fallback mechanisms for oversized prompts and connection retries.

### Operations, Troubleshooting, and Testing

- **[BROWSER_AUTOMATION_RUNBOOK.md](BROWSER_AUTOMATION_RUNBOOK.md)**
  - Diagnostic steps for Patchright and Chromium automation issues.
  - Connecting Chrome DevTools protocol (CDP) for live inspection.
  - Cleaning stale singleton lock files (`SingletonLock`, `SingletonSocket`, `SingletonCookie`).
  - Handling orphan browser processes and memory considerations.

- **[TESTING_AND_VERIFICATION.md](TESTING_AND_VERIFICATION.md)**
  - Running unit tests with `python -m unittest discover -s tests -v`.
  - Checking environment variable documentation accuracy via `scripts/generate_env_reference.py --check`.
  - Running manual browser diagnostic scripts (`scripts/diagnose_chatgpt.py`, `scripts/diagnose_gemini.py`, `scripts/test_multi_turn.py`).
  - Guidelines for adding new regression tests.

