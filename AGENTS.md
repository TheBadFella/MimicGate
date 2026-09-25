# MimicGate Repository Instructions

## Project overview

MimicGate Gateway is a Python 3.11-3.14 FastAPI service that exposes browser-backed AI providers through OpenAI-compatible APIs. Preserve the browser-driven design unless the user explicitly asks for a different integration.

The project was renamed from CatGPT. Keep the public compatibility aliases working: the `catgpt-browser` model ID, the `x-catgpt-*` request headers, the `catgpt` console script, the `CatGPTApp` class, and the `CATGPT_*` environment variables are still supported. New code should prefer the MimicGate names.

Important areas:

- `src/chatgpt/`: ChatGPT UI client, model registry, response detection, and media handling.
- `src/claude/`: Claude UI client and selectors.
- `src/browser/`: persistent browser management, login, stealth, and tab handling.
- `src/api/`: native, OpenAI-compatible, Ollama-compatible, and conversation-routing APIs.
- `src/selectors.py`: ChatGPT selectors. Add new selectors before older fallbacks.
- `tests/`: focused unit and integration-style tests.
- `scripts/`: manual browser and end-to-end diagnostics.
- `docs/`: architecture, API, environment, model-switching, and testing guidance.

## Working conventions

- Inspect the relevant implementation, tests, and documentation before editing.
- Preserve unrelated user changes in a dirty worktree.
- Keep changes focused and follow existing async and typing patterns.
- Use type hints where reasonable and keep functions small.
- Do not use em dashes in repository documentation.
- Never commit credentials, `.env` contents, cookies, browser profiles, personal data, or captured provider content.
- When environment variables change, update `scripts/generate_env_reference.py` as needed and regenerate the environment reference.

## Validation

Prefer the locked `uv` environment:

```bash
uv sync --frozen --group dev
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python scripts/generate_env_reference.py --check
```

Run focused tests first while iterating. Run the full suite for changes that affect shared routing, browser state, model switching, or API compatibility.

Useful focused commands include:

```bash
uv run --frozen python -m unittest tests.test_chatgpt_client_model_switch -v
uv run --frozen python -m unittest tests.test_browser_tab_pool -v
uv run --frozen python -m unittest tests.test_conversation_store -v
```

Browser smoke scripts interact with a live provider account. Run them only when live interaction is in scope:

```bash
uv run python scripts/check_page_state.py
uv run python scripts/diagnose_chatgpt.py
uv run python scripts/test_multi_turn.py
```

## Chrome DevTools MCP

Use the dedicated Chrome DevTools MCP when the user requests remote-debugging, DevTools inspection, or validation against an authenticated Chrome session. Do not confuse it with a separate in-app browser or browser-extension control surface.

Expected local MCP configuration:

```toml
[mcp_servers.chrome-devtools]
command = "npx"
args = ["chrome-devtools-mcp@latest", "--autoConnect"]
```

Before connecting, Chrome remote debugging must be enabled at `chrome://inspect/#remote-debugging`, and the user must approve Chrome's connection prompt when it appears.

DevTools safety rules:

- Limit inspection and interaction to tabs and URLs explicitly placed in scope by the user.
- Do not inspect unrelated tabs, cookies, storage, credentials, saved data, or personal content.
- Prefer DOM/accessibility snapshots and targeted evaluation over screenshots or broad page dumps.
- Do not submit prompts, change account settings, delete conversations, or perform other persistent actions unless the user requested them.
- Use a temporary new-chat tab for comparisons when possible. Close temporary tabs and restore menus or focus after testing.
- Avoid reproducing sensitive page contents in logs or the final response.
- Remind the user to disable remote debugging when live testing is finished.

## ChatGPT model-picker behavior

The ChatGPT composer can show only the current effort label, such as `Instant`, while Advanced exposes both the concrete model and effort. Therefore:

- An initial Advanced check can be necessary for an explicit model/version request.
- Reopening Advanced for every turn in the same conversation is unnecessary when the model and effort were already verified.
- Cache verification at the correct page or conversation scope. Invalidate it after navigation, an external model change, a different requested model, or uncertain UI state.
- Requests using `mimicgate-browser` (or the legacy `catgpt-browser` alias) should preserve the browser-selected model unless a default model or reasoning effort explicitly requires a change.
- Test existing-chat reuse and clean new-chat behavior separately because browser and conversation state can differ.

For model-switching changes, review `src/chatgpt/client.py`, `src/chatgpt/model_registry.py`, `src/config.py`, `docs/MODEL_AND_REASONING_SELECTION.md`, and `tests/test_chatgpt_client_model_switch.py` together.

## Documentation and handoff

- Update user-facing docs when behavior, configuration, or API contracts change.
- Report what changed, which tests ran, and any live-browser limitations.
- Keep private browser observations generalized; do not quote unrelated conversation content.

## Repository skills

- For documentation, UI prose and change summaries, read [unslop-catgpt](.agents/skills/unslop-catgpt/SKILL.md).
- For verification, read [verify-catgpt](.agents/skills/verify-catgpt/SKILL.md).
- For implementation, debugging or review, read [change-catgpt](.agents/skills/change-catgpt/SKILL.md).

Load the relevant skill, not the full catalog. These workflows preserve the user's scope and the repository's specific contracts. [Source revisions and licenses](.agents/skill-provenance.md).
