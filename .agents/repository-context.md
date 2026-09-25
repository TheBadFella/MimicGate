# CatGPT engineering context

Preserve browser-backed ChatGPT/Claude sessions and OpenAI/Ollama API compatibility.

Stack observed on 2026-09-06: Python FastAPI browser gateway. Recheck manifests and scoped instructions when the implementation changes.

## Read for the affected area

- `src/chatgpt/client.py`
- `src/chatgpt/model_registry.py`
- `src/browser`
- `src/api`
- `tests/test_chatgpt_client_model_switch.py`
- `tests/test_browser_tab_pool.py`
- `pyproject.toml`
- `.github/workflows/ci.yml`

## Contracts to preserve

- Model selection and effort must match the requested conversation; preserve browser-selected models when no override is requested.
- Keep async cancellation, tab ownership, conversation isolation, selector fallbacks and streamed response ordering intact.
- Browser sessions, captured conversations and credentials are private. Live provider prompts require task authorization.

## Verification recipes

These commands were found in project instructions, manifests, tests or CI and reviewed for task fit. Their inclusion does not mean they ran or passed during the skill audit. Inspect test fixtures and environment prerequisites before execution. Run only checks relevant to the change; keep any stricter repository release gate.

| Working directory | Command | Purpose / condition |
|---|---|---|
| root | `uv run --frozen python -m unittest tests.test_chatgpt_client_model_switch tests.test_browser_tab_pool -v` | Focused model/tab regressions |
| root | `uv run --frozen python -m unittest discover -s tests -v` | Shared routing/API/browser-state changes |
| root | `uv run --frozen python scripts/generate_env_reference.py --check` | Environment documentation |

## Observable proof

Use offline fixtures for routing and stream shape; an authorized live browser test must separately cover reused chats and new chats. Record model/effort and resulting state without recording private conversation contents.

## Communication

Use CatGPT Gateway consistently. Distinguish API compatibility from a direct provider API integration. Do not invent supported model names or claim a live browser test passed from unit tests.
