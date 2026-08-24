# Testing CatGPT

CatGPT uses a locked `uv` environment for repeatable local and CI tests.

```bash
uv sync --frozen --group dev
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python scripts/generate_env_reference.py --check
```

The CI workflow runs the same checks on Python 3.11 and 3.14. Update dependencies with `uv lock --upgrade`, review the lockfile diff, and rerun the full suite before committing.

## Container checks

Validate the Compose model without starting services:

```bash
docker compose config --quiet
docker build -f docker/Dockerfile -t catgpt:test .
```

The container persists the browser profile, logs, and durable conversation database beneath `${DOCKERDIR}/appdata/catgpt`. The SQLite database stores conversation text in plaintext.

## Browser smoke checks

Use a dedicated development Chrome profile or a trusted remote-debugging session. The diagnostic scripts are intentionally manual because they interact with the live provider UI:

```bash
uv run python scripts/check_page_state.py
uv run python scripts/diagnose_chatgpt.py
uv run python scripts/test_multi_turn.py
```

For API-level verification, start CatGPT and exercise these cases:

1. Call `/v1/models` and confirm the live ChatGPT model/reasoning variants appear.
2. Send two turns with the same `conversation_id`; confirm the second call reuses the thread and does not duplicate verified history.
3. Change an earlier message under that ID; confirm CatGPT starts a new thread.
4. Send `X-CatGPT-Thread-Mode: fresh`; confirm it does not reuse a prior thread.
5. If `CHATGPT_PROJECT_URL` is configured, confirm every resulting `/c/...` URL remains under the project.
6. Exercise `tool_choice` values `none`, `required`, and a named function.

Never enable remote debugging on a personal browser profile unless every connected tool is trusted; the debugging protocol grants access to tabs, cookies, and site data.
