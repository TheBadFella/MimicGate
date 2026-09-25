---
name: verify-catgpt
description: Choose and run proportionate verification for CatGPT changes using its existing tests and operational boundaries. Use before claiming a fix works or when assessing missing proof.
---

# Verify CatGPT

Read [repository context](../../repository-context.md) for commands, prerequisites and contracts. Read scoped AGENTS files for the changed area. This is a verification recipe, not a claim that an app instance is available.

1. Define the observable result from the user's request. Select the existing test, CLI, UI or configuration check that can distinguish correct behavior from this failure.
2. Inspect setup/teardown, environment loading, network calls and filesystem targets. Use isolated fixture state. Establish which process, data directory and port belong to this run before driving an app. Do not infer safety from a command named test, check or dry-run.
3. Run the smallest useful check, then broaden for shared contracts or the repository's required release gate. A regression test must fail for the reported defect; avoid tests that duplicate the implementation or merely inspect source text.
4. If UI or external behavior matters, record the action and resulting state at the real interface when the environment and authorization allow it. A screenshot alone, compilation, HTTP 200 or a mocked unit test cannot establish all side effects.
5. Keep evidence sufficient to reproduce the result: working directory, command, exit status, observed result and relevant skips. Exclude secrets and private account/media/household contents. Stop processes this run created by their owned handles, preserve evidence, and remove only identified temporary state.
6. Report passed, failed and not-run checks separately. Missing tools, live access or an unavailable OS are limitations, not passes. Do not widen production access to make a check pass. Continue safe local work and state what remains unverified.

For prose-only changes, inspect the diff, links and technical meaning; application test suites are not automatically required. For skill changes, validate frontmatter, links and routing examples.

Adapted from Pstack verification and proof principles. [Sources and licenses](../../skill-provenance.md).
