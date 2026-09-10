@AGENTS.md

# Claude Code specifics
Everything shared with other agents is in `AGENTS.md` above. This file holds only
what Claude Code does differently.

## Rule modules
`.claude/rules/*.md` load automatically alongside this file; no need to read them
explicitly. Project `AGENTS.md` overrides a module on conflict.

## Subagents
`.claude/agents/` ships three on `model: haiku`: `scout` (read-only lookup),
`test-runner` (run checks, return a digest), `doc-updater` (mechanical `.md` edits).
Delegate the mechanical steps to them; keep design and every code change in the main
session. `haiku` resolves through `ANTHROPIC_DEFAULT_HAIKU_MODEL`, so on a third-party
endpoint it is that provider's small model. The built-in `Explore` inherits the main
model — use `scout` when a cheap answer is enough.

## Hooks
`.claude/settings.json` lints every edited file after Edit/Write (advisory, never
blocks) and warns at session start when `ANTHROPIC_BASE_URL` points at a
non-Anthropic endpoint. Do not run `audit-diff` in such a session.
