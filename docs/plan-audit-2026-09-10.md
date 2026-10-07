# Implementation plan audit (2026-09-10)

Independent audit of `docs/history/plan.md` before handing it to the implementer.
Checked: `docs/history/plan.md`, `docs/acceptance.md`, `AGENTS.md`, `CLAUDE.md`,
`DECISIONS.md`, every module in `.claude/rules/`, plus `Makefile`,
`pyproject.toml`, `ruff.toml`, `.github/workflows/ci.yml`,
`docker-compose.yml`, `Dockerfile`, `frontend/vite.config.ts`. Conducted by
Claude Code (Claude Fable 5.1) as a second model; the plan's author took no part
in the audit.

## Findings by decreasing severity

### 1. Integration-test isolation is incompatible with race tests
- Where: commit 3 — "a transaction with rollback per test".
- What breaks: tests 3 (two coroutines on the last unit), 14
  (`FOR UPDATE SKIP LOCKED`), 6 (webhook from the stub), 2/18 (SSE after commit)
  need separate connections and real commits. Inside one shared transaction,
  row locks and visibility do not work; two coroutines on one `AsyncSession` is
  a broken test. Four of the nine acceptance tests cannot be written as described.
- Fix: TRUNCATE (or a separate schema) per test, real commits; `get_db` in
  tests hands out ordinary sessions from the pool.

### 2. The order of steps in `/pay` rests on coding discipline
- Where: commit 12 — "reservation into `paying`, call the stub, status from the
  response"; the guard `WHERE status='pending'` is described only for the webhook.
- What breaks: (a) a double click on "pay" calls the stub twice —
  `payments.order_id UNIQUE` protects only if the INSERT is made and committed
  before the HTTP call; (b) a webhook that arrives before the handler's commit
  does not find `provider_ref` and is lost; (c) a stub timeout handled by a
  rollback returns the reservation to `held`, even though the stub may have
  approved the payment.
- Fix: the backend generates `provider_ref` itself; in one transaction, INSERT
  `payments` + `reservations held→paying` + commit, then call the stub; timeout =
  the order stays `pending`. Add the test `test_double_pay_calls_paystub_once`
  (the stub received exactly one POST): `test_double_pay_same_key_one_order`
  covers "two orders" but not "charge twice".

### 3. Spec items with no backend commit and no test
- Where: commits 22 and 23 — frontend only.
- What breaks: there is no shop statistics endpoint (stock, sold, in carts,
  revenue, list of stuck payments) and no `GET /api/me/orders`. The "decline"
  outcome is not defined or tested anywhere.
- Fix: a backend commit "shop stats + my orders" between 16 and 17; the test
  `test_declined_payment_returns_reservation_to_cart` (see answer 1).

### 4. `make up` per the README will not produce a working app
- Where: commit 25 — "run `make up` from a clean `.env`"; the Dockerfile CMD is
  uvicorn only.
- What breaks: nobody applies migrations and the seed in compose; the stub does
  not know the backend address for `callback_url` (a setting like
  `PUBLIC_BASE_URL` is needed and is not in commit 1's list); in CI after commit 3
  there is no `DATABASE_URL` (`.env` does not exist there).
- Fix: an entrypoint or `command` with `alembic upgrade head` + seed; a setting
  for the webhook address; `env:` in the backend job in ci.yml in commit 3.

### 5. Commit order
- Commit 13 (test 5: payment survives hold expiry) needs the expiry mechanism
  from commit 14. Swap them.
- Commit 17 retrofits broadcast into the code of commits 8, 9, 12, 14, 16.
  Introduce a broadcaster interface with a no-op implementation in commit 8.

### 6. `make check` will not be green after every commit
- `vite.config.ts` holds a 60 % lines/statements threshold; commits 19–23 add
  components, and the only test comes in 24. The same goes for
  `--cov-fail-under` from commit 1 on two tiny tests.
- `make test` = all of `pytest tests/`, so from commit 3 on a local `make check`
  needs the DB up; `make test-integration` is mentioned, but the targets are not
  split.
- Fix: tests in every frontend commit; set the coverage threshold at commit 3
  (the first real suite); README: "`make check` requires `docker compose up -d db`".
  Scope of the frontend threshold — see answer 6.

### 7. Test 1 is labelled wrongly
- Where: test table, row 1 — "unit, frozen clock"; commit 7.
- What breaks: "cannot buy before the start" is guaranteed by
  `WHERE starts_at <= :now` in commit 8's UPDATE. A unit test can only check the
  Python duplicate of the check, not the guarantee. The second half of the item
  ("for everyone at the same time") has no test at all.
- Fix: both tests are integration tests in commit 8; in State — "partially proven".

### 8. Settings and the time source
- Commit 1 lists eight settings and in the same breath says "only those already
  read" — a contradiction. `SECRET_KEY` has no consumer anywhere in the plan
  (server-side random session tokens are not signed). `HOLD_MINUTES` is a fixed
  value from the spec, not a knob.
- The claim "Ruff DTZ catches `datetime.now()`" is wrong twice: DTZ is not in
  `select` in `ruff.toml`, and DTZ catches naive datetimes, so
  `datetime.now(UTC)` passes. There is no mechanical check for "a single time
  source"; `server_default=func.now()` in models is a habit that will break it.
- Fix: in commit 1 only `APP_ENV`, `LOG_LEVEL`; remove `SECRET_KEY`;
  `HOLD_MINUTES` is a constant; a separate grep test for
  `datetime.now`/`func.now`/`now()`.

### 9. State machines are not defined
- The plan nowhere lists the reservation/order/payment statuses and transitions;
  `sales.status` is both a stored column and a computation from time. Commits 8,
  12, 13, 14, 16 will each invent their own piece.
- Fix: enums and a transition table in commit 4; `sales.status` is only a
  terminal flag (`ended`), everything else is derived from `starts_at/ends_at`
  and `:now`.

### 10. Verify before relying on
- httpx `ASGITransport` in known versions buffers the whole response body —
  test 2/18 (two SSE clients) will hang through it. Either uvicorn on a free
  port, or test the broadcaster + SSE generator directly.
- The frozen clock must reach the scheduler and SSE: a `create_app(clock=…)`
  factory and a `run_once(now)` on the scheduler are needed, otherwise test 4
  will wait on `sleep`.
- In-process webhook delivery: the stub needs an injectable HTTP client pointed
  at the backend's ASGI app; the plan does not describe this.

## Scope
Not required by the spec, but worth the time (user decisions, not errors):
registration/roles/argon2; HMAC on the webhook; a reconciliation loop (which is
also a second "resolver" racing the webhook — dropped by answer 4).
Required by the spec, but deferred/missing: findings 3, 4, the stub timeout
semantics (closed by answer 5).

## Implicit decisions (the implementer would pick on their own)
1. Declined payment: the reservation goes back to `held` with the old
   `expires_at`, or is released. → answer 1.
2. Decline after the sale ends: the item must not return to the storefront.
3. Payment after `expires_at` but before the scheduler tick, and after `ends_at`
   but before cleanup: a time guard in the UPDATE, or nondeterminism from the
   polling interval. → answer 3.
4. One reservation per buyer per sale (partial UNIQUE) or any number.
   → answer 2.
5. Idempotency-Key scope (per user) and handling IntegrityError on a
   concurrent duplicate.
6. Who generates `provider_ref` (see finding 2).
7. The "card number → outcome" table is given only in the "Verification" section.
8. Scheduler polling interval.
9. Who applies migrations and the seed in compose and CI.
10. `available` on "withdraw unsold": zero it or change only the status.

## Questions to the human and answers (2026-09-10)
1. **Declined payment.** The reservation returns to the cart: `paying → held`,
   `expires_at` unchanged, the item does not return to the storefront. Retrying
   payment is allowed.
2. **Per-buyer limit.** One active reservation per buyer per sale
   (partial UNIQUE on `(sale_id, user_id)` for non-terminal statuses).
3. **Payment after expiry.** The deadline is checked right in the
   `held → paying` transition:
   `UPDATE reservations SET status='paying' WHERE id=? AND status='held'
   AND expires_at > :now AND :now < sale.ends_at`. Zero rows → 409. Behaviour
   does not depend on the scheduler's polling interval.
4. **Reconciliation with the stub.** Not needed. The webhook and a manual
   `resolve` on the stub are enough. Commit 16 loses "reconciliation of `pending`
   payments"; the stub's `GET /payments/{ref}` stays for debugging.
5. **"Stuck".** Both a `pending` response and an HTTP timeout; both leave the
   order in `pending` (the `payments` row is already committed before the call,
   see finding 2). The demo shows the former — via a card number.
6. **Frontend coverage threshold.** Counted only over `src/stores` and `src/api`
   (`coverage.include` in `vite.config.ts`); components and screens are not part
   of the threshold.
7. **`SECRET_KEY`.** Remove it from the settings list.
