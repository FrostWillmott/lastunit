# lastunit

[![CI](https://github.com/FrostWillmott/lastunit/actions/workflows/ci.yml/badge.svg)](https://github.com/FrostWillmott/lastunit/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/github/license/FrostWillmott/lastunit)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](ruff.toml)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Dependabot](https://img.shields.io/badge/Dependabot-enabled-025E8C?logo=dependabot&logoColor=white)](.github/dependabot.yml)

![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Vue 3](https://img.shields.io/badge/Vue-3-4FC08D?logo=vuedotjs&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![PostgreSQL 17](https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white)

## What it is

Flash-sale service: a shop lists a batch of goods at a special price for a
short window, and there are more buyers than stock. A buyer reserves one unit
(10-minute hold) and pays through a payment stub; the shop watches stock, sold
and revenue update live. Spec: `docs/acceptance.md` (Russian). Plan:
`docs/plan.md`.

## Tools and models

Started from a scaffolding template — Claude Code's `workflow-scaffolding`
skill plus a Vite + Vue 3 + TypeScript frontend skeleton.

Built with Claude Code: the repository's own conventions live in `AGENTS.md`,
`.claude/rules/` and `.claude/skills/`, and the agent reads them every session.
The work was split across models on purpose, in separate sessions:

- **Claude Fable 5.1** — the judgement-heavy steps, and no implementation: the
  scaffold and the plan (`docs/plan.md`), then every independent review —
  `docs/plan-audit-2026-09-10.md` and `docs/code-audit-2026-09-12.md`, which
  also carries the security review.
- **DeepSeek V4 Pro** — the implementation: stages 0-8 and the docs, plus the
  fixes each audit asked for. It reviewed its own work as it went by running
  `/code-review`, which executes as a separate agent in a session of its own —
  eleven runs across the three stage-building sessions.
- **Claude Opus 5** — the two jobs that meant observing the running system from
  outside: repairing a CI pipeline that had been failing unnoticed, and the
  end-to-end runtime check (`docs/verification-2026-09-12.md`), which reads
  screenshots and so can check what the app actually renders — something V4 Pro
  cannot do — plus the fixes that came out of it.

The split is the point: a mistake has to survive a different model in a
different session before it reaches the repository, and both audits found
defects that the implementer's own review had passed. The full per-session
tool/model record lives in `agent-sessions/`.

## Stack

- Backend: FastAPI (Python 3.12, uv), async SQLAlchemy + PostgreSQL 17.
- Frontend: Vue 3 + TypeScript (Vite).
- Payment and email are stubs by design.

## Prerequisites

- Docker with compose — for the database and the local stack.
- Python 3.12 — pinned in `.python-version`; uv reads it and fetches the
  interpreter, so no system Python is required. `requires-python` in
  `pyproject.toml` is the separate, lower floor this code supports.
- uv >= 0.12.11 — Python dependency manager. The floor is `[tool.uv] required-version`
  in `pyproject.toml`; uv enforces it itself and CI reads it from there. A newer uv
  is fine. The Dockerfile names one exact version instead, for reproducible images.
- Node 24.15.0 — run `nvm install` in the repo root: it reads `.nvmrc`, installs
  that version and switches to it (`nvm use` alone fails when it is missing).
  `npm ci` hard-fails on anything older (`engine-strict` in `frontend/.npmrc`);
  the exact patch is required by `abbrev` and `nopt` in the lockfile.

## Run locally

```bash
make install   # make env (generates secrets) + uv sync + npm ci
make up        # docker compose: db + backend + frontend
```

Frontend at http://localhost:8080, backend at http://localhost:8000 (all routes
under `/api`). `.env` is never committed and has no default password: `make env`
generates the secrets, and `docker compose` refuses to start without them.
`make up` (and `make seed`) also creates a demo shop account — `shop@example.com`
/ `shop-password`, seeded only when `APP_ENV != prod` — so you can log into the
shop screen, plus a demo flash sale (5 units, starts a minute after the seed) so
the storefront has something live to show. Payment is a stub (`paystub/`, port
8001): card `…0000` approves, `…0002` declines, `…9995` hangs until you resolve
it on `localhost:8001/docs`.

## Configuration

`make env` copies `.env.example` to `.env` and fills empty secrets with
`openssl rand`. Defaults live in `.env.example` — the single source of truth.

| Variable | What it changes |
|---|---|
| `APP_ENV` | `dev` enables API docs; `prod` disables them and marks the session cookie Secure. |
| `LOG_LEVEL` | Backend app log verbosity. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Database role, password (generated), name. |
| `SESSION_TTL_DAYS` | Login-cookie lifetime, in days. |
| `SEED_SHOP_EMAIL` / `SEED_SHOP_PASSWORD` | Demo shop account (`make seed`), dev-only. |
| `VITE_API_URL` | Backend origin the Vite dev proxy forwards `/api` to. |

## Testing

```bash
make check             # backend lint + format + typecheck + tests, then frontend checks
make test-unit         # unit tests only, no database
make test-integration  # integration tests against a real Postgres
```

`make check` and `make test` need a running database first: `docker compose up -d db`.
Unit tests (`tests/unit/`) need no I/O; integration tests (`tests/integration/`)
hit the real Postgres.

A green `make check` says the suite passes, not that the assembled app works.
The latter was checked separately by driving the running stack through a browser:
[`docs/verification-2026-09-12.md`](docs/verification-2026-09-12.md).

## State

Every "Ожидаемое поведение" bullet in `docs/acceptance.md` maps to one named
test. Rows are updated as each stage lands.

All nine bullets were also exercised against the running stack in a browser on
2026-09-12 — what was driven, what was measured and what was found is in
[`docs/verification-2026-09-12.md`](docs/verification-2026-09-12.md).

| # | Expected behaviour | Proving test | Status |
|---|---|---|---|
| 1 | No purchase before start; opens for everyone at start | `test_reserve_before_start_rejected`, `test_reserve_at_start_allowed`, `test_create_sale_broadcasts_sale_status_to_open_clients`, `StorefrontView.test.ts` (button disabled before start, refetch when the tab returns) | proven |
| 2 | Stock changes live on every open client | `test_stock_event_reaches_second_client`, `test_sse_smoke_real_server`, `test_payment_result_broadcasts_sale_stats_to_everyone` (shop figures) | proven |
| 3 | Last unit sells to one of two buyers | `test_last_unit_two_buyers_one_wins` | proven |
| 4 | Hold expires after 10 min, stock returns, seen live | `test_hold_expires_returns_stock`, `test_hold_expiry_broadcasts` | proven |
| 5 | Payment started before expiry completes even if the stub answers late | `test_payment_started_before_expiry_completes_after` | proven |
| 6 | Hung payment keeps the order pending; resolves later | `test_hung_payment_keeps_stock`, `test_hung_payment_resolves_via_webhook`, `test_paystub_timeout_keeps_order_pending` | proven |
| 7 | Double "pay" is one order, one charge | `test_double_pay_same_key_one_order`, `test_double_pay_calls_paystub_once`, `test_start_payment_with_stale_hold_in_session_reports_pending_payment` | proven |
| 8 | Exactly one order email | `test_order_email_sent_exactly_once` | proven |
| 9 | Sale end clears holds, removes unsold, notifies owners | `test_sale_end_clears_holds_and_notifies` | proven |
| T11 | Two open tabs stay in sync | `test_stock_event_reaches_second_client` (2 clients) + `useRealtime.test.ts` fan-out + `sales.test.ts` `applies two successive stock events and reflects each` | proven |

How bullet 1 is met, precisely: the ban before the start is enforced by the
backend (`409` on reserve), so it holds whatever a client believes the time is.
The storefront's own gate is a countdown anchored to the backend — each response
carries `server_now` and the client keeps the offset — so a viewer whose own
clock is wrong still sees the sale open at the right instant (checked with a
browser clock set 10 minutes fast). What is *not* claimed is simultaneity to the
second: the flip is a client-side timer, and a browser throttles timers in a
backgrounded tab, so such a tab can lag until it is focused again, at which
point it refetches and re-anchors.

Accepted edge cases:

- A payment declined after a sale has ended clears the reservation and cancels
  the order without returning the unit — `available` is already 0 at that point,
  so there is nothing to return (see DECISIONS.md).
- A card declined *during* a live sale leaves the hold in place: the order stays
  `pending`, the unit stays in the buyer's cart for the rest of the ten minutes,
  and paying again with another card completes it. Still one email per order.

## Decisions worth knowing

- Invariants live in the database (`CHECK` / partial `UNIQUE`), not in Python;
  payments are attempts with at most one `pending` per order.
- One time source — Postgres, via a `Clock` and a `:now` parameter; no
  `datetime.now()` in business logic.
- Sale times are absolute, entered in the shop's IANA zone and stored as UTC.
- Full log: `DECISIONS.md`.

## Next steps

The plan (`docs/plan.md`) is complete. Left for a future iteration:

- Postgres `LISTEN/NOTIFY` and a separate worker, so several backend processes
  fan out the same live events (the demo runs one uvicorn process with an
  in-memory broadcaster).
- An automatic hung-payment timeout and reconciliation with the payment stub.
- Pagination on the list endpoints.
