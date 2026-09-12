# lastunit

Flash-sale service: a shop lists a batch of goods at a special price for a
short window, and there are more buyers than stock. A buyer reserves one unit
(10-minute hold) and pays through a payment stub; the shop watches stock, sold
and revenue update live. Spec: `docs/acceptance.md` (Russian). Plan:
`docs/plan.md`.

Started from a scaffolding template — Claude Code's `workflow-scaffolding`
skill plus a Vite + Vue 3 + TypeScript frontend skeleton. Built with Claude
Code (CLI): the implementation (stages 0-8) was written by deepseek-v4-pro on a
non-Anthropic endpoint, while the scaffold, plan and audit sessions used Claude
Fable 5.1. The full per-session tool/model record lives in `agent-sessions/`.

## Stack

- Backend: FastAPI (Python 3.12, uv), async SQLAlchemy + PostgreSQL 17.
- Frontend: Vue 3 + TypeScript (Vite).
- Payment and email are stubs by design.

## Prerequisites

- Docker with compose — for the database and the local stack.
- uv — Python dependency manager (Dockerfile and CI pin `0.12.11`).
- Node 24.15.0 — `.nvmrc` in the repo root, so `nvm use` picks it up from
  there. `frontend/package.json` repeats the floor in `engines` and
  `frontend/.npmrc` sets `engine-strict=true`, so `npm ci` refuses an older
  Node instead of failing later with a confusing error. 24.15.0 is not
  cosmetic: `abbrev` and `nopt` in the lockfile require `^24.15.0`.

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

## State

Every "Ожидаемое поведение" bullet in `docs/acceptance.md` maps to one named
test. Rows are updated as each stage lands.

| # | Expected behaviour | Proving test | Status |
|---|---|---|---|
| 1 | No purchase before start; opens for everyone at start | `test_reserve_before_start_rejected`, `test_reserve_at_start_allowed` | partially proven |
| 2 | Stock changes live on every open client | `test_stock_event_reaches_second_client`, `test_sse_smoke_real_server`, `test_payment_result_broadcasts_sale_stats_to_everyone` (shop figures) | proven |
| 3 | Last unit sells to one of two buyers | `test_last_unit_two_buyers_one_wins` | proven |
| 4 | Hold expires after 10 min, stock returns, seen live | `test_hold_expires_returns_stock`, `test_hold_expiry_broadcasts` | proven |
| 5 | Payment started before expiry completes even if the stub answers late | `test_payment_started_before_expiry_completes_after` | proven |
| 6 | Hung payment keeps the order pending; resolves later | `test_hung_payment_keeps_stock`, `test_hung_payment_resolves_via_webhook`, `test_paystub_timeout_keeps_order_pending` | proven |
| 7 | Double "pay" is one order, one charge | `test_double_pay_same_key_one_order`, `test_double_pay_calls_paystub_once`, `test_start_payment_with_stale_hold_in_session_reports_pending_payment` | proven |
| 8 | Exactly one order email | `test_order_email_sent_exactly_once` | proven |
| 9 | Sale end clears holds, removes unsold, notifies owners | `test_sale_end_clears_holds_and_notifies` | proven |
| T11 | Two open tabs stay in sync | `test_stock_event_reaches_second_client` (2 clients) + `useRealtime.test.ts` fan-out + `sales.test.ts` `applies two successive stock events and reflects each` | proven |

Accepted edge case: a payment declined after a sale has ended clears the
reservation and cancels the order without returning the unit — `available` is
already 0 at that point, so there is nothing to return (see DECISIONS.md).

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
