# Implementation plan

## Context
The repository started from a scaffold (tooling, CI, agent rules, an empty
`FastAPI()` in the root `main.py`, a Vue stub with a single `/api/health` request).
Stage 0 is done: the backend is an `app/` package with a `create_app()` factory, `GET /api/health`
and unit tests; `make check` is green.
The spec is `docs/acceptance.md`: a limited-sale service where there are more buyers
than goods. The plan splits the implementation into stages with logical commits so
the history shows gradual work (a requirement of the spec), and records the
decisions made.

Ground rules for every commit: `make check` is green (starting from stage 0),
`DECISIONS.md` is extended in the same commit where a decision is made, README does
not lag behind the code. Branch `main` (locally and on origin), commits go straight
to it, push after every stage.

Revision 2026-09-10: the plan went through an independent audit by a second model
(`docs/plan-audit-2026-09-10.md`); the edits below close its findings and the
user's answers. The decisions are recorded in `DECISIONS.md` under the same date.

What the `.claude/rules/` modules dictate is not repeated here: invariants in the DB,
idempotency, outbox, `SKIP LOCKED`, UTC and `timestamptz`, money in `BIGINT`,
test structure and the State table — `transactional-web.md`, `testing.md`,
`config-hygiene.md`, `documentation.md`. Below is only what the modules leave
for the project to choose.

## Decisions made (2026-09-10, with the user; details in `DECISIONS.md`)
| Point | Decision |
|---|---|
| D1 Sign-in | **Login and password.** `users(email UNIQUE, password_hash, role)`; passwords are argon2id via `pwdlib`. Server-side sessions: token `secrets.token_urlsafe(32)`, its SHA-256 stored in the `sessions` table, cookie HttpOnly + SameSite=Lax, Secure depending on `APP_ENV`. No signing, `SECRET_KEY` is not needed. The `shop` role grants access to the shop screen; the seed creates one shop user. |
| D2 Realtime | **SSE** `GET /api/events`, VueUse `useEventSource`. |
| D3 Topology | **One uvicorn process**: API + scheduler (lifespan task) + in-process broadcaster. LISTEN/NOTIFY and a separate worker are the "next iteration" in README. |
| D4 Payment stub | **A separate HTTP service** `paystub/` (its own FastAPI, its own Dockerfile, a service in compose). The outcome depends on the card number; "hanging" = status `pending` until `resolve` is called. The answer arrives as a webhook; the stub retries an undelivered webhook. There is no automatic reconciliation: the shop screen has a "check status" button that asks the stub and applies the answer with the same handler as the webhook. |
| D5 Payments as attempts | One order per reservation; `payments` are payment attempts, at most one in `pending` at a time (partial UNIQUE). A declined attempt leaves the reservation (`paying → held`, `expires_at` unchanged) and the order (`pending`) in place until the hold expires; a retry is a new attempt on the same order. |
| D6 Per-buyer limit | One active reservation per buyer per sale: partial UNIQUE `(sale_id, user_id) WHERE status IN ('held','paying')`. |
| D7 Payment after expiry | The deadline is checked in the `held → paying` transition itself: `UPDATE ... WHERE status='held' AND expires_at > :now AND :now < ends_at`. Zero rows → 409. The behaviour does not depend on the scheduler interval. |
| D8 "Hung" | Both a `pending` answer and an HTTP timeout from the stub: both leave the attempt and the order in `pending`, the goods stay held. The demo shows the former via the card number. |
| D9 Frontend coverage | The threshold is computed only over `src/stores` and `src/api` (`coverage.include`, justified by a comment in `vite.config.ts`); components and screens are not part of the threshold. |

Decisions made along the way (also in `DECISIONS.md`):
- **One time source — the Postgres clock.** Python has no `datetime.now()` in
  business logic and there is no `now()` inside SQL expressions (including `server_default=func.now()`
  in models). Instead there is a `Clock` protocol: the production implementation runs `SELECT now()`
  once per transaction and hands that instant to the service; the service passes it to all
  queries as the `:now` parameter (`WHERE starts_at <= :now`, `expires_at = :now + interval`)
  and returns it to the client as `server_now`. The test implementation is `frozen_clock`
  (`testing.md`). `Clock` enters the application through the `create_app(clock=...)` factory,
  which both the scheduler and SSE use. The client computes timers as an offset from
  `server_now`, so that "the start is simultaneous for everyone" does not depend on the browser clock.
  Mechanical check: `tests/unit/test_no_local_time.py` greps for
  `datetime.now`, `datetime.utcnow`, `func.now`, `time.time`, `date.today` in
  `app/` and fails on any occurrence (Ruff DTZ is no good for this: it is not in
  `select`, and it lets `datetime.now(UTC)` through). A bare `now()` is deliberately not
  forbidden — Clock implements `SELECT now()`.
- **Sale time is absolute, in the shop's IANA zone.** `sales.timezone`
  (an IANA name) is a column; `POST /api/sales` takes `timezone` + local
  `starts_at`/`ends_at`, normalizes them to UTC via `ZoneInfo` and stores `timestamptz`.
  Buyers see only the countdown from `server_now`, they do not need the zone (there is
  no column on `users`). `ZoneInfo` is not caught by the time-source grep check.
- **Stock**: an `available` counter on the sale, an atomic
  `UPDATE sales SET available = available - 1 WHERE id=? AND available > 0 AND starts_at <= :now AND :now < ends_at RETURNING`
  + `CHECK (available >= 0)`. "Sold" and "in carts" are derived counters over statuses.
- **Hung payment and end of sale**: per the spec, a hung order waits for the stub's
  answer, and the goods are not returned. When the sale ends, only carts
  in `held` are cleared; reservations in `paying` stay until the answer. A decline after
  `ends_at` moves the reservation to `cleared`, not to `held`: the goods are not
  returned to the storefront. There is no automatic timeout; this goes into README as deliberate behaviour.
- **Server downtime**: jobs that came due during downtime run at
  startup (fire late). Record this in README.
- **`HOLD_MINUTES = 10`** is a constant in `app/services/cart.py`, not a setting:
  the spec fixes the value, nobody has a reason to turn the knob.

## State machines
Defined by enums in commit 4; every transition is `UPDATE ... WHERE status=<from>`
with a rowcount check, zero rows → 409 or a no-op.

| Entity | Statuses | Transitions |
|---|---|---|
| `sales` | `active` \| `ended` | only the terminal `ended` is stored (set by the scheduler when `ends_at <= :now`). "Not started yet / in progress" is derived from `starts_at`, `ends_at` and `:now`; in the API it is the computed field `phase`. |
| `reservations` | `held` → `paying` → `sold`; `held` → `expired` (scheduler, 10 min); `held` → `released` (buyer); `held` → `cleared` (end of sale); `paying` → `held` (attempt declined before `ends_at`); `paying` → `cleared` (declined after `ends_at`) | `expired`, `released` and `cleared`-from-`held` return a unit to `available` in the same transaction; `cleared`-from-`paying` does not (the sale has ended). |
| `orders` | `pending` → `paid`; `pending` → `cancelled` | one order per reservation (`reservation_id UNIQUE`), created by Idempotency-Key. `cancelled` is set together with `expired`/`released`/`cleared` on the reservation. A declined attempt does not change the order (D5). |
| `payments` | `pending` → `approved` \| `declined` | an attempt per order; partial UNIQUE `(order_id) WHERE status='pending'`; `provider_ref` is generated by the backend before the stub is called. The result is applied by one function `apply_payment_result(provider_ref, outcome, now)` — from the synchronous answer, the webhook and the "check status" button. |

## Expected behaviour → tests (future README "State" table)
Numbers are from `docs/acceptance.md`; "two tabs" is requirement 11 of the same file.

| # | Expected behaviour | Test | Layer |
|---|---|---|---|
| 1 | Cannot buy before the start; at the start it opens for everyone | `test_reserve_before_start_rejected`, `test_reserve_at_start_allowed`. "For everyone at once" has no separate test: the client computes the timer from `server_now`, in State — "partially proven" | integration, frozen clock |
| 2 | Stock changes for everyone without a page reload | `test_stock_event_reaches_second_client` (broadcaster + SSE generator), `test_sse_smoke_real_server` (uvicorn) | integration |
| 3 | The last unit cannot be sold to two buyers | `test_last_unit_two_buyers_one_wins` | integration, 2 coroutines, 2 connections |
| 4 | The cart holds for 10 minutes, then returns, everyone sees it | `test_hold_expires_returns_stock`, `test_hold_expiry_broadcasts` | integration |
| 5 | A payment started before expiry completes even if the answer comes later | `test_payment_started_before_expiry_completes_after` | integration |
| 6 | The stub "hung": order pending, goods are neither returned nor sold twice; after the answer it is settled | `test_hung_payment_keeps_stock`, `test_hung_payment_resolves_via_webhook`, `test_paystub_timeout_keeps_order_pending` | integration |
| 7 | Double "pay": one order, one charge | `test_double_pay_same_key_one_order`, `test_double_pay_calls_paystub_once` | integration |
| 8 | One email per order | `test_order_email_sent_exactly_once` | integration, outbox |
| 9 | At the end: unsold goods withdrawn, carts cleared, owners notified | `test_sale_end_clears_holds_and_notifies` | integration |
| T11 | Two tabs | covered by 2 + a store test on two events + a `useRealtime` fan-out test | frontend |
| — | A declined attempt returns the goods to the cart, the order stays alive (D5) | `test_declined_attempt_returns_reservation_to_cart` | integration |
| — | "Check status" applies the answer like a webhook (D4) | `test_check_status_applies_result_like_webhook` | integration |

## Stages and commits

### Stage 0 — working backend scaffold (2 commits)
1. `feat(backend): package layout, settings, health route`
   - `main.py` → `app/main.py` with a `create_app(clock=..., broadcaster=...)` factory;
     `app/config.py` on pydantic-settings. Per `config-hygiene.md` a field is added
     only together with its consumer, so here there are only `APP_ENV` and `LOG_LEVEL`.
     The rest appear in the consuming commits: `DATABASE_URL` (3),
     `SESSION_TTL_DAYS` (5), `SEED_SHOP_EMAIL/PASSWORD` (6), `PAYSTUB_URL`,
     `PAYSTUB_WEBHOOK_SECRET`, `PUBLIC_BASE_URL` (12). There is no `SECRET_KEY` (D1).
   - pyproject: `dependencies` + `[dependency-groups] dev` (pytest, pytest-asyncio,
     httpx, mypy, pytest-cov). `asyncio_mode = "auto"`, mypy strict. The
     `--cov-fail-under` threshold is switched on in commit 5, when the first real
     test suite appears (`testing.md`, Coverage section).
   - `GET /api/health`; `tests/unit/test_config_env_contract.py`;
     `tests/unit/test_no_local_time.py` (grep check of the time source).
   - Delete `test_main.http`.
2. `docs: README with required sections and State table (all "not proven")`
   - Sections from `documentation.md`. Mention of the template and the model/tool.
     The State table refers to the numbers from `docs/acceptance.md`.

### Stage 1 — DB and data model (2 commits)
3. `feat(db): async engine, session dependency, alembic baseline`
   - `app/db.py`, `alembic/` with an async env; `tests/integration/conftest.py`:
     the real DB from compose, **TRUNCATE of all tables before every test, real
     commits** — the race tests (3, 4, 5, 6) and SSE after commit need separate
     connections, and rollback-per-test breaks them. `get_db` in tests hands out ordinary
     sessions from the pool.
   - Uncomment `services: db` in ci.yml and add `env: DATABASE_URL`
     to the backend job (there is no `.env` in CI).
   - Makefile: `make test` = unit + integration (needs the DB up),
     `make test-unit`, `make test-integration`. README: "`make check` needs
     `docker compose up -d db`".
   - Docker: the backend entrypoint runs `alembic upgrade head` before uvicorn,
     so that `make up` from a clean `.env` gives a working application.
4. `feat(db): domain tables, enums and constraints`
   - `users`, `sessions(token_hash UNIQUE, user_id, expires_at)`,
     `sales(title, price_minor, quantity, available, starts_at, ends_at, timezone, status)`
     with `CHECK (available >= 0)`, `CHECK (starts_at < ends_at)`, an index on `(status, ends_at)`,
     `reservations(sale_id, user_id, status, expires_at, released_at)` with an index on
     `(status, expires_at)` and partial UNIQUE `(sale_id, user_id) WHERE status IN ('held','paying')` (D6),
     `orders(reservation_id UNIQUE, user_id, sale_id, amount_minor, status, idempotency_key, UNIQUE(user_id, idempotency_key))`,
     `payments(order_id, provider_ref UNIQUE, status, requested_at, resolved_at)`
     with partial UNIQUE `(order_id) WHERE status='pending'` (D5),
     `notifications(kind, entity_id, recipient, payload, sent_at, UNIQUE(kind, entity_id))`.
   - Status enums and the transition table from the "State machines" section —
     in `app/models/enums.py`, one source for all subsequent commits.
   - The migration is read by hand; the constraints are listed in DECISIONS.

### Stage 2 — authentication (2 commits)
5. `feat(auth): register, login, logout with server-side sessions`
   - `app/services/auth.py`, `app/routers/auth.py`; argon2id via `pwdlib`;
     session token `secrets.token_urlsafe(32)`, SHA-256 in the DB, cookie HttpOnly,
     SameSite=Lax, Secure when `APP_ENV != "dev"` (D1); `current_user` and
     `require_shop` dependencies. Unit tests for the hash and for an expired session;
     an integration test for registration with a duplicate email → 409.
     This is where `--cov-fail-under` is switched on at the number reached.
6. `feat(auth): shop role and seed shop user`
   - `make seed` creates the shop user from `.env` (`SEED_SHOP_EMAIL/PASSWORD`);
     the entrypoint from commit 3 calls the seed after migrations (idempotently).

### Stage 3 — sale and hold (3 commits)
7. `feat(sales): create/list sales with server time`
   - `GET /api/sales`, `GET /api/sales/{id}` (+`server_now`, `phase`), `POST /api/sales`
     for the shop role (`available = quantity` on creation). `POST` takes
     `timezone` (IANA) and local `starts_at`/`ends_at`; the backend normalizes them
     to UTC via `zoneinfo.ZoneInfo` and stores `timestamptz` + `timezone` for display.
     Unit tests of the pure function `phase(starts_at, ends_at, now)` and of converting
     local time to UTC, including a DST boundary; test 1 lives in commit 8,
     because the before-start ban is a condition in SQL, not in Python.
8. `feat(cart): reserve one unit with 10-minute hold`
   - `POST /api/sales/{id}/reserve` → atomic UPDATE; 409 "sold out" /
     "not started yet" / "already in cart" (D6). Test 3 (two coroutines, two
     connections, the last unit) and test 1 (both halves, frozen clock).
   - `app/realtime.py`: a `Broadcaster` interface with a no-op implementation, passed into
     `create_app`; the service publishes `stock_changed` after commit already here, so that
     commit 18 does not rewrite five modules.
9. `feat(cart): release hold and view my cart`
   - `DELETE /api/reservations/{id}` (`held → released`, the order, if any, →
     `cancelled`), `GET /api/me/cart`. A test for returning the unit.

### Stage 4 — order and payment stub (5 commits)
10. `feat(paystub): standalone payment stub service`
    - `paystub/` as a separate package in the same repo: `POST /payments`
      (`reference` from the backend, amount, card, `callback_url`) → `approved` /
      `declined` / `pending` depending on the card number; `POST /payments/{ref}/resolve` for
      hung ones; `GET /payments/{ref}` — status for the "check status" button.
      Webhook to `callback_url` with an HMAC signature; on a non-2xx or a timeout the stub
      retries delivery (3 attempts with growing backoff, state in memory).
      The card table is fixed here and in README:
      `…0000` approved, `…0002` declined, `…9995` pending.
    - The stub's outgoing HTTP client is injected (`create_app(http_client=...)`),
      so that in the backend's integration tests the webhook goes to the backend's
      ASGI application in-process: the real HTTP contract without a network.
    - Its own Dockerfile, a `paystub` service in compose, port 8001; `known-first-party`
      in `ruff.toml` gets `paystub` added. Unit tests of the stub, including the webhook retry.
11. `feat(orders): create order with Idempotency-Key`
    - `POST /api/orders` (reservation_id + header). The key is unique paired with
      `user_id`; a repeated key → the same response, no second row is created;
      a parallel duplicate is caught by `IntegrityError` and re-read.
      `amount_minor` is a snapshot of the price. Test 7 (first half).
12. `feat(payments): pay through paystub, webhook, guarded transitions`
    - `POST /api/orders/{id}/pay`. The order of steps is fixed, and that is the
      guarantee: (1) one transaction — `reservations held→paying` with the check
      `expires_at > :now AND :now < ends_at` (D7), INSERT of an attempt into `payments` with
      a `provider_ref` generated by the backend, the order stays `pending`;
      commit; (2) call the stub with `reference = provider_ref` and
      `callback_url = PUBLIC_BASE_URL + /api/payments/webhook`; (3) a synchronous
      `approved`/`declined` is applied via `apply_payment_result`; `pending`
      and a timeout change nothing (D8). A second click hits the partial UNIQUE
      on the `pending` attempt before any HTTP.
    - `POST /api/payments/webhook`: HMAC check, then `apply_payment_result`:
      `UPDATE payments ... WHERE provider_ref=? AND status='pending'`; only when
      rowcount = 1, in the same transaction: `approved` → `orders paid`,
      `reservations paying→sold`; `declined` → `reservations paying→held`
      (or `cleared` if `ends_at <= :now`), the order does not change (D5).
    - Settings `PAYSTUB_URL`, `PAYSTUB_WEBHOOK_SECRET`, `PUBLIC_BASE_URL`
      (the backend address the stub sees from the compose network).
    - Tests: 6 (`keeps_stock`, `resolves_via_webhook`, `timeout_keeps_order_pending`),
      7 (`calls_paystub_once`), `declined_attempt_returns_reservation_to_cart`.
13. `feat(scheduler): expire holds with SKIP LOCKED poll loop`
    - `app/scheduler.py` in lifespan; `FOR UPDATE SKIP LOCKED` over `held` with
      `expires_at <= :now`; `expired` + `available + 1` + order `cancelled` in one
      transaction; fire late at startup. A public `run_once(session, now)` — tests
      call it directly, without waiting for the loop. Test 4 (first half).
14. `feat(payments): payment started before hold expiry completes`
    - A reservation in `paying` is not picked up by `run_once`. Test 5: reserve at T,
      pay at T+9 (`pending` card), `run_once(T+11)`, resolve → `sold`.
      Comes after 13, because test 5 needs the expiry mechanism.

### Stage 5 — outbox, end of sale, screens (3 commits)
15. `feat(outbox): notifications, email stub, sender loop`
    - `app/email_stub.py` writes to the log and `sent_at`. The order email
      (`kind='order_paid'`, `entity_id=order_id`) in the same transaction as `paid`. Test 8.
16. `feat(sales): end-of-sale cleanup`
    - `run_once` takes `sales` with `ends_at <= :now AND status='active'`
      `FOR UPDATE SKIP LOCKED`: `status='ended'`, `available=0`, `held → cleared`
      (orders → `cancelled`) with a `kind='cart_cleared'` notification,
      `entity_id=reservation_id`; `paying` is not touched. Test 9.
17. `feat(api): shop stats, payment status check, buyer orders`
    - `GET /api/shop/sales/{id}/stats` (stock, sold, in carts, revenue,
      list of `pending` attempts with `provider_ref`), `POST /api/shop/payments/{ref}/check`
      (a `GET /payments/{ref}` request to the stub → `apply_payment_result`),
      `GET /api/me/orders`. Integration tests for the counters after
      reserve/pay/expire and `test_check_status_applies_result_like_webhook`.

### Stage 6 — live updates (2 commits)
18. `feat(realtime): SSE endpoint and in-process broadcaster`
    - `GET /api/events`; the production `Broadcaster` instead of the no-op; events
      `stock_changed`, `sale_status`, `order_status`. Publishing after commit from
      the same places where the outbox is written (scheduler, payment, webhook).
19. `test(realtime): two clients see the same stock change`
    - Test 2 and test 4 (second half): two `Broadcaster` subscribers + the SSE
      generator, a mutation through the API, both received the event. Plus one smoke
      `test_sse_smoke_real_server`: uvicorn on a free port in a separate task,
      one `httpx` client reads the stream (httpx `ASGITransport` buffers the whole
      response, so SSE cannot be read through it).

### Stage 7 — frontend (6 commits)
Every commit carries tests for its own store/api module: the coverage threshold is computed
over `src/stores` and `src/api` (D9), and `make check` must stay green.
20. `feat(frontend): router, pinia, typed api client, auth screens`
    - Add `vue-router`, `pinia`, `@vueuse/core`; `src/api/` following the backend types;
      registration and login forms; a route guard by role. `coverage.include`
      in `vite.config.ts` → `src/stores/**`, `src/api/**` with a justifying comment.
      API client tests.
21. `feat(frontend): storefront with stock and countdown`
    - `useRealtime()`; the `sales` store; a timer based on `server_now`; the "add to cart" button
      disabled until the start. A test of the `sales` store.
22. `feat(frontend): cart and checkout`
    - Hold timer; "pay" with an Idempotency-Key and disabled while the
      request is in flight; after a decline — "try again" (a new attempt); a card field
      with a hint of the test numbers from commit 10. A test of the `cart` store.
23. `feat(frontend): buyer cabinet` — orders and statuses, updated over SSE. A test of the `orders` store.
24. `feat(frontend): shop dashboard` — stock, sold, in carts, revenue;
    creating a sale (date-time picker + IANA zone selection); a list of hung
    attempts with a "check status" button
    (commit 17) and a link to the stub's resolve. A test of the `shop` store.
25. `test(frontend): store applies two realtime events` — half of "two tabs".

### Stage 8 — submission (2 commits)
26. `feat: seed sale and compose smoke run`
    - `make seed` adds a sale "starts in 1 minute, 5 units".
      A `make up` run from a clean `.env` following README (migrations and seed — the entrypoint).
27. `docs: final State table, next steps, session exports`
    - README: real statuses of all rows; "Next steps" (LISTEN/NOTIFY, worker,
      timeout for hung payments, automatic reconciliation with the payment provider, pagination);
      `agent-sessions/` with the exports.

Total: 27 commits, 9 stages. Push to GitHub after every stage.

## Verification
- Every commit: `make check` with the DB up (`docker compose up -d db`);
  `make test-unit` without it.
- After stage 7: `make up` from scratch, two browser windows (a normal and a private one, two
  buyers), a manual run of scenarios 1, 3, 4, 6, 7; the hang is checked with
  the `…9995` card, then with the resolve button at `localhost:8001/docs` or "check
  status" on the shop screen; a decline — with the `…0002` card.
- Before submission: `make ci`, `make audit`, `make docker-build`.

## Critical files
- Existing: `Makefile`, `docker-compose.yml`, `Dockerfile`, `.github/workflows/ci.yml`
  (uncomment db, add `DATABASE_URL`), `frontend/vite.config.ts`
  (proxy `/api`, `coverage.include`), `frontend/nginx.conf`, `frontend/src/api.ts`
  (will become `src/api/`), `ruff.toml` (`known-first-party`).
- To appear: `app/{main,config,db,scheduler,realtime,email_stub}.py`,
  `app/{models,routers,services}/`, `alembic/`, `paystub/`, `tests/{unit,integration}/`,
  the backend entrypoint.
