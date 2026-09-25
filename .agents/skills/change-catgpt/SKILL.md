---
name: change-catgpt
description: Implement, diagnose or review CatGPT behavior changes against the user's intent and repository contracts. Use for features, bugs or refactors; use unslop-catgpt for prose-only edits.
---

# Change CatGPT

Read [repository context](../../repository-context.md) and applicable AGENTS instructions. Inspect the affected implementation, tests and current Git status before editing. Preserve pre-existing changes.

## Resolve intent

State the requested behavior and observable acceptance condition. Use repository terminology. Investigate code and existing decisions before asking questions; ask only when an unresolved choice materially changes the outcome. Do not turn a small fix into an interview, issue-tracker setup or redesign. Record a durable decision only when it captures a real tradeoff future work needs.

## Diagnose and implement

For a bug, seek a focused reproduction of the user's symptom. If it requires unavailable production access, continue source analysis with hypotheses clearly labeled; do not claim reproduction. Test a falsifiable hypothesis with a targeted probe, then fix the responsible code and remove temporary instrumentation.

For behavior with a useful automated test interface, use one failing regression or feature test, implement the smallest coherent change, and rerun it. Reuse the established test interface rather than requiring a new approval for every test. Keep external calls replaceable at existing interfaces. Tests should observe real outputs and side effects with independent expected values.

Preserve the contracts in the repository context. Prefer existing modules and simple data structures; remove unnecessary new abstractions only when callers and tests prove they are redundant. Do not delete defensive checks, compatibility handling, comments or fallbacks merely because they look repetitive. Propose larger architectural work separately when it exceeds the request.

## Review the result

Compare two dimensions separately: does the change implement the requested behavior, and does it preserve repository contracts? Trace affected callers, serialized data, scheduling/retry behavior, migrations and external consumers when relevant. Give each finding a concrete file/location, failure scenario and supporting evidence. Treat style smells as judgment calls, not demonstrated bugs.

Review the actual work in scope: staged, unstaged and relevant untracked files for local work; a resolved merge-base for branch review. Do not review only HEAD when the user asks about uncommitted changes. Use the conversation as acceptance criteria when no spec exists. A missing spec limits review; it does not justify inventing one or publishing tickets.

Use [verify-catgpt](../verify-catgpt/SKILL.md) for relevant checks. Complete both review dimensions locally unless independent agents are explicitly authorized and useful. Repository skills do not themselves grant permission to send messages, commit/push/merge, spend provider credits or deploy services.

Report changed behavior, evidence and unresolved limitations. Route prose through [unslop-catgpt](../unslop-catgpt/SKILL.md) without changing technical meaning.

Adapted from Matt Pocock diagnosis/TDD/review/domain-design and Pstack blast-radius/simplicity. [Sources and licenses](../../skill-provenance.md).
