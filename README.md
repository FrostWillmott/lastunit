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

## Configuration

`make env` copies `.env.example` to `.env` and fills empty secrets with
`openssl rand`.

| Variable | Default | What it changes |
|---|---|---|
| `APP_ENV` | `dev` | `dev` enables API docs; `prod` disables them (later: Secure cookies). |
| `LOG_LEVEL` | `INFO` | Backend log verbosity. |
| `POSTGRES_USER` | `app` | Database role. |
| `POSTGRES_PASSWORD` | — | Database password (generated). |
| `POSTGRES_DB` | `app` | Database name. |

## Testing

```bash
make check      # backend lint + format + typecheck + tests, then frontend checks
```

Backend tests live in `tests/unit/` (no I/O); integration tests against the real
database arrive in `docs/plan.md` stage 1 and will need `docker compose up -d db`.

## State

Every "Ожидаемое поведение" bullet in `docs/acceptance.md` maps to one named
test. As of this scaffold no product behaviour is implemented, so every row is
"not proven".

| # | Expected behaviour | Proving test | Status |
|---|---|---|---|
| 1 | No purchase before start; opens for everyone at start | `test_reserve_before_start_rejected`, `test_reserve_at_start_allowed` | not proven |
| 2 | Stock changes live on every open client | `test_stock_event_reaches_second_client`, `test_sse_smoke_real_server` | not proven |
| 3 | Last unit sells to one of two buyers | `test_last_unit_two_buyers_one_wins` | not proven |
| 4 | Hold expires after 10 min, stock returns, seen live | `test_hold_expires_returns_stock`, `test_hold_expiry_broadcasts` | not proven |
| 5 | Payment started before expiry completes even if the stub answers late | `test_payment_started_before_expiry_completes_after` | not proven |
| 6 | Hung payment keeps the order pending; resolves later | `test_hung_payment_keeps_stock`, `test_hung_payment_resolves_via_webhook`, `test_paystub_timeout_keeps_order_pending` | not proven |
| 7 | Double "pay" is one order, one charge | `test_double_pay_same_key_one_order`, `test_double_pay_calls_paystub_once` | not proven |
| 8 | Exactly one order email | `test_order_email_sent_exactly_once` | not proven |
| 9 | Sale end clears holds, removes unsold, notifies owners | `test_sale_end_clears_holds_and_notifies` | not proven |
| T11 | Two open tabs stay in sync | store test feeding two realtime events | not proven |

## Decisions worth knowing

- Invariants live in the database (`CHECK` / partial `UNIQUE`), not in Python;
  payments are attempts with at most one `pending` per order.
- One time source — Postgres, via a `Clock` and a `:now` parameter; no
  `datetime.now()` in business logic.
- Sale times are absolute, entered in the shop's IANA zone and stored as UTC.
- Full log: `DECISIONS.md`.

## Next steps

Follow `docs/plan.md` — stage 1 is the database schema, async session and
migrations. Planned but not in scope yet: Postgres `LISTEN/NOTIFY` for
multi-worker fan-out, a hung-payment timeout, automatic reconciliation with the
payment stub, and pagination.
