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

- Use short, descriptive branch names that identify the work, such as `fix/...` or `feat/...`. Use lowercase words separated by hyphens; avoid issue/PR numbers, dates, agent names and vague placeholders in the branch name. Recheck the name when the scope changes.

### Documentation is part of every merged PR

- Assess documentation impact while implementing the change, including configuration, CLI/API behavior, defaults, limits, errors, recovery and effects on existing files/services. Dependency and internal-only PRs still need this assessment; do not make artificial documentation edits when usage is unchanged.
- User/operator instructions live in the repository guides and documentation. Update existing task guides or references when behavior or requirements change.
- Prepare affected documentation edits alongside the code PR. Include guide links and documentation plan in the description, or a specific explanation of why no user-facing documentation changes are needed.
- After **every PR merge**, review the final merged diff, publish applicable documentation changes within the authorized publication boundary, and verify live links and anchors.
- Keep release state accurate. Describe merged-but-unreleased behavior in a clearly marked upcoming section with its PR/commit; retain instructions for the published version.
- Verify steps and labels against code and available runtime evidence. Cover expected outcomes, limits, data/job effects and troubleshooting for known failure modes.
- Preserve existing page URLs and section anchors when reorganizing guides, or leave compatible anchors/links. Check internal cross-references after moving content.
- The final merge handoff must say which documentation was published, with links, or why no update was necessary. Instructions to read code or tests are not documentation.

### PR descriptions and maintainer voice

- Before creating or editing a PR description, reread the final prose for clarity and voice, and check the published body after writing it.
- Write as the maintainer explaining a concrete change to another person: what was awkward or broken, what users can do now, and why this approach fits. Use a short natural paragraph for small PRs. Headings are optional; remove unused template sections, `N/A` filler and repeated scaffolding.
- First person is welcome when supported by the work (for example, "I moved the cutoff warning beside the download action so it is visible before confirmation"). Do not invent personal experiences, motivations, excitement, anecdotes or user feedback to manufacture a personal touch. Prefer plain words; avoid promotional openings, em dashes and canned summaries.
- Keep implementation details only when they help review correctness or a tradeoff. Summarize checks proportionately: relevant results, a CI/evidence link and material gaps. Preserve failures, exclusions and not-run distinctions without pasting a command diary or repeating the same test totals several times.
- Include documentation impact and credit external contributors/reporters where relevant. Preserve authorship/license requirements without asserting work is original when it is not. Rewrite the title/body around the final scope if the change evolves.
- For release descriptions, follow the project's release-note conventions: skimmable feature-focused bullets, named contributor thanks and direct usage-guide links. Do not substitute autogenerated PR/dependency lists for maintainer release notes.

### UI Visual Review Checklist

Complete this review during UI work and before reporting the change as finished:

- Before coding, identify the shared component and variant that fit the control's context. Embedded field icons should use the field-action style; standalone outlined buttons can create unwanted nested borders inside an outlined field.
- Render the changed UI with synthetic data and inspect actual browser screenshots. Review empty, populated, selected, focused, hovered, disabled, expanded, and error states where applicable. Include long labels and values.
- Check at 320px, 390px, 768px, and 1440px, plus any widths requested by the user. Inspect borders, icon size, alignment, spacing, text clipping, dropdown placement, and neighboring controls. Passing geometry checks alone does not establish visual consistency.
- Verify keyboard access, visible focus, focus restoration after clearing or closing, and at least 44px touch targets on phone layouts. Hide selection actions when nothing is selected and clear actions when there is no value to clear.
- For shared component or CSS changes, inspect callers and render representative affected screens. Put reusable corrections in the shared component or semantic theme class.
- Fix visual defects found in this review before presenting the result. When showing before/after screenshots, use matching data and viewport sizes.
- Report the browser widths and states checked, relevant automated checks, and any missing visual verification. If browser review is unavailable, state that gap rather than claiming the UI is visually verified.
