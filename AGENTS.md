# AGENTS.md
Guidance for any coding agent working in this repository. `CLAUDE.md` includes
this file and adds Claude Code specifics; other agents read this file directly.

## Where the rest lives
- Conventions: `.claude/rules/*.md`. Claude Code loads them automatically; every
  other agent reads them explicitly. `_LEVELS.md` defines the MUST / MUST-UNLESS /
  PREFER tags used in each module.
- Skills: `.claude/skills/` (also reachable as `.agents/skills`, a symlink).
- Decision log: `DECISIONS.md`. Spec: `docs/acceptance.md`. Session exports: `agent-sessions/`.

## Project
Flash-sale service: a shop lists a batch of goods at a special price for a
short window and there are more buyers than stock. The spec is `docs/acceptance.md` (Russian);
its "Ожидаемое поведение" bullets are the acceptance criteria. Backend: FastAPI
on Python 3.12 (uv). Frontend: Vue 3 + TypeScript (Vite, npm). Storage:
PostgreSQL 17 via docker-compose. Payment and email are stubs by design.

Status: scaffold only. The backend is a bare `FastAPI()` in root `main.py`, there
are no models, routes or `tests/`, and `README.md` and `.env.example` are empty.

## Active rule modules
python-core, backend-fastapi, testing, config-hygiene, transactional-web,
frontend-vue, documentation. Every file in `.claude/rules/` applies.

## Architecture divergences
3-layer split (`routers/` → `services/` → DB session), NOT full Clean
Architecture. No repository layer: services call SQLAlchemy directly.

Scaffold mismatches to reconcile before the first backend change (each spans
several files, so none is visible from one file alone):
- The Dockerfile runs `app.main:app` and `ruff.toml` sets `known-first-party = ["app"]`,
  but the code lives in root `main.py`. The intended layout is an `app/` package;
  move `main.py` there rather than editing the Dockerfile.
- `make check` cannot pass yet: `pyproject.toml` declares only fastapi and uvicorn
  (no pytest, pytest-asyncio, mypy) and `tests/` does not exist. Makefile and CI
  install with `uv sync --all-extras`, the image with `UV_NO_DEV=1`, so dev tooling
  belongs in dev dependencies/extras, not in `dependencies`.
- The frontend calls `/api/health`, which the backend does not serve. `test_main.http`
  is IDE boilerplate for routes that do not exist.

## Commands
```bash
make install   # uv sync + npm ci
make up        # docker compose: db + backend + frontend
make check     # backend lint+format+types+tests, then frontend-check — run before finishing any task
make fix       # ruff --fix + format, prettier --write
make audit     # uv audit + npm audit
make ci        # check + frontend-build + audit — exactly what GitHub Actions runs

# single test
uv run pytest tests/unit/services/test_order.py::test_name -v
cd frontend && npx vitest run src/App.test.ts
```

Backend and frontend are separate origins in dev; the browser only ever talks to
`/api/*`, which Vite proxies to `localhost:8000` and nginx proxies inside compose.
Mount every backend route under `/api`.

## Verification matrix
`make check` covers all rows; this is for knowing which failure is yours.

| Changed | Required | Also run when |
|---|---|---|
| `app/**` | `make lint typecheck test` | migrations touched → `make test` against real DB (`make up`) |
| `frontend/**` | `make frontend-check` | build output matters → `make frontend-build` |
| `pyproject.toml`, `uv.lock`, `frontend/package*.json` | `make audit` | — |
| `Dockerfile*`, `docker-compose.yml` | `make docker-build` | — |
| `.env.example` or the Settings class | `make test` (the env-contract test) | — |

## Spec deliverables that shape every session
From `docs/acceptance.md`, not derivable from code:
- Every expected-behaviour bullet maps to one named test and one row in the
  README "State" table (bullet → test → pass/fail). A bullet without a test is
  listed as "not proven", never dropped.
- The reviewer checks that work happened gradually: small, frequent commits and
  dated `DECISIONS.md` entries in the same change as the decision. Do not batch
  a day of work into one commit.
- README must say the repo started from a scaffolding template and which AI
  tool and model were used. Agent use is expected and is not to be hidden.
- Session logs go to `agent-sessions/` at the end of each session and once more,
  as a full export, before submission.
- Two clients open at once (two tabs) must stay in sync; see the "Live updates"
  rules in `transactional-web.md`.

## Key design decisions
See [`DECISIONS.md`](DECISIONS.md) for the full, dated log.

## Git
- Agent use is part of the deliverable, so session links and tool references in
  commit messages are welcome. Skip co-author lines.
- Small, frequent commits with real timestamps; the spec asks for a visible
  timeline.
