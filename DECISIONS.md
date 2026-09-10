# Decisions

Append-only log of non-obvious choices — not a changelog of every commit.
Newest entry at the top. See `documentation.md` in the rules-library for the
convention. Don't edit past entries; if a decision is reversed, add a new one
that supersedes it.

<!--
## YYYY-MM-DD — <short title>
<One or two lines: the decision and why. Link related files/PRs if useful.>
-->

## 2026-09-10 — No default secrets in compose; `make env` generates them
`docker-compose.yml` declares secrets as required (`${VAR:?message}`), so a run
without `.env` fails with the variable name instead of booting with a password
everyone knows. Defaults stay only for non-secret values (user, database name).
`.env.example` lists every variable compose reads with secrets left empty;
`make env` copies it and fills the empty ones with `openssl rand`, and
`make install` / `make up` call it first so a clean checkout is still one command.

## 2026-09-10 — Agent entry point is AGENTS.md
`AGENTS.md` holds the shared guidance; `CLAUDE.md` is `@AGENTS.md` plus Claude-only
sections (Anthropic's recommended pattern). `.agents/skills` symlinks to
`.claude/skills` so Codex and audits find the skills at the standard path.

## 2026-09-10 — Rule modules and layering
Active modules: python-core, backend-fastapi, testing, config-hygiene,
transactional-web, frontend-vue, documentation. Modules not needed by a
flash-sale demo were deleted rather than left inactive. Backend is the 3-layer
routers/services/db split without a repository layer.
