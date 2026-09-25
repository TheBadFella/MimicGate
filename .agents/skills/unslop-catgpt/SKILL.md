---
name: unslop-catgpt
description: Edit CatGPT documentation, UI prose and change summaries for plain, precise language while preserving technical meaning and the project's tone. Use for prose cleanup or unslop requests, not code refactoring.
---

# Unslop for CatGPT

Read the applicable repository instructions. Work only on the prose requested or already being changed.

1. Identify the reader and what they need to understand or do. Preserve the author's point, scope and uncertainty.
2. Remove promotional claims, generic openings/conclusions, repeated labels, unnecessary jargon and filler. Prefer concrete subjects, active verbs and consistent terminology. Split sentences that require rereading.
3. Keep evidence, qualifications that affect accuracy, source links and useful lists/tables. Never invent a number, opinion, personal experience or test result to make the writing sound human.
4. Preserve commands, code fences, paths, identifiers, schemas, placeholders, quoted source text and license notices. Comments that explain operational constraints keep those facts. Prompts and tool descriptions can change behavior; treat substantive rewrites as behavior changes with the appropriate checks.
5. Use restrained formatting and the repository's release/document style. Avoid gratuitous em dashes and decorative emphasis; do not mechanically replace punctuation inside code or required templates. Useful parentheses, colons and real technical terms are allowed.
6. Compare the result with the original: same claims and instructions, clearer reading, no lost consent, warning or operational constraint. Report what changed and any factual claim left unverified.

## Project voice

Use CatGPT Gateway consistently. Distinguish API compatibility from a direct provider API integration. Do not invent supported model names or claim a live browser test passed from unit tests.

For code-quality cleanup, use the repository's engineering workflow and tests. This skill edits language; it does not authorize deleting guards, compatibility code, tests or documentation.

Adapted from Pstack Unslop and technical-writing. [Sources and licenses](../../skill-provenance.md).
