# lastunit

Flash-sale service: a shop lists a batch of goods at a special price for a
short window, and there are more buyers than stock. A buyer reserves one unit
(10-minute hold) and pays through a payment stub; the shop watches stock, sold
and revenue update live. Spec: `docs/acceptance.md` (Russian). Plan:
`docs/plan.md`.

Started from a scaffolding template — Claude Code's `workflow-scaffolding`
skill plus a Vite + Vue 3 + TypeScript frontend skeleton. Built with Claude
Code (CLI); the scaffold, plan and audit sessions used Claude Fable 5.1, and
the full per-session tool/model record lives in `agent-sessions/`.

## Stack

- Backend: FastAPI (Python 3.12, uv), async SQLAlchemy + PostgreSQL 17.
- Frontend: Vue 3 + TypeScript (Vite).
- Payment and email are stubs by design.

## Prerequisites

- Docker with compose — for the database and the local stack.
- uv — Python dependency manager (Dockerfile and CI pin `0.12.11`).
- Node 24 — see `frontend/.nvmrc`.

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
shop screen. Payment is a stub (`paystub/`, port 8001): card `…0000` approves,
`…0002` declines, `…9995` hangs until you resolve it on `localhost:8001/docs`.

## Configuration

`make env` copies `.env.example` to `.env` and fills empty secrets with
`openssl rand`. Defaults live in `.env.example` — the single source of truth.

| Variable | What it changes |
|---|---|
| `APP_ENV` | `dev` enables API docs, `prod` disables them (later: Secure cookies). |
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
| 2 | Stock changes live on every open client | `test_stock_event_reaches_second_client`, `test_sse_smoke_real_server` | proven |
| 3 | Last unit sells to one of two buyers | `test_last_unit_two_buyers_one_wins` | proven |
| 4 | Hold expires after 10 min, stock returns, seen live | `test_hold_expires_returns_stock`, `test_hold_expiry_broadcasts` | proven |
| 5 | Payment started before expiry completes even if the stub answers late | `test_payment_started_before_expiry_completes_after` | proven |
| 6 | Hung payment keeps the order pending; resolves later | `test_hung_payment_keeps_stock`, `test_hung_payment_resolves_via_webhook`, `test_paystub_timeout_keeps_order_pending` | proven |
| 7 | Double "pay" is one order, one charge | `test_double_pay_same_key_one_order`, `test_double_pay_calls_paystub_once` | proven |
| 8 | Exactly one order email | `test_order_email_sent_exactly_once` | proven |
| 9 | Sale end clears holds, removes unsold, notifies owners | `test_sale_end_clears_holds_and_notifies` | proven |
| T11 | Two open tabs stay in sync | `sales.test.ts` `applies two successive stock events and reflects each` | proven |

## Decisions worth knowing

- Invariants live in the database (`CHECK` / partial `UNIQUE`), not in Python;
  payments are attempts with at most one `pending` per order.
- One time source — Postgres, via a `Clock` and a `:now` parameter; no
  `datetime.now()` in business logic.
- Sale times are absolute, entered in the shop's IANA zone and stored as UTC.
- Full log: `DECISIONS.md`.

## Next steps

Follow `docs/plan.md` — stage 7 is the frontend. Planned but not in scope yet:
Postgres `LISTEN/NOTIFY` for multi-worker fan-out, a hung-payment timeout,
automatic reconciliation with the payment stub, and pagination.
