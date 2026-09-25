# Skill sources and adaptation

Audited 2026-09-06. These are curated local adaptations, not complete upstream installations. Keep this repository's rules and the user's task scope authoritative. No models, hooks, permissions or external agents are configured by these skills.

- [Pstack](https://github.com/cursor/plugins/tree/93b00b89ef425a9c1bac0d0b317dfc49c930ac99/pstack/skills), commit `93b00b89ef425a9c1bac0d0b317dfc49c930ac99`: Unslop, technical-writing, verification design, blast-radius, boundary/type discipline and simplicity principles.
- [Matt Pocock](https://github.com/mattpocock/skills/tree/3cca18b368ae95cdbdebbff572ccafa662551015/skills), commit `3cca18b368ae95cdbdebbff572ccafa662551015`: diagnosing-bugs, TDD, code-review, domain-modeling, codebase-design and writing-for-agents.

Local changes: precise repository triggers; prose-only Unslop boundaries; source-backed verification recipes; existing tests as the default test interface; sequential review allowed; no assumed Skill tool, task tracker, paid provider calls or automatic publish/merge. Preserve protocol terms, mandatory disclosures and repository-specific release styles. Verification recipes are reviewed guidance, not certified end-to-end browser/server harnesses.

To update, compare the pinned upstream files and this repo's manifests/tests, review the diff, then validate the edited skills. Do not overwrite local adaptations with a bulk installer. The original audit and rollback journal are at `D:/Git/skill-audit-2026-09-06` on the auditing workstation.

## Pstack license

MIT License

Copyright (c) 2026 Lauren Tan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Matt Pocock license

MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

