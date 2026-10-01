# Code audit (2026-09-12)

Independent audit of the range `efdaea8..HEAD` (56 commits, `934fcfe`) by a
second model: Claude Code (CLI), Claude Fable 5.1. The implementation was done by
deepseek-v4-pro following `docs/plan.md`. Nothing in the repository was changed;
the only file created is this report. The experiments (scenarios E1–E8 below)
were run by scripts outside the repository against the test DB `app_test` and
against a clone brought up per the README.

Scale: **critical** — an acceptance item does not hold in the delivered build;
**high** — README/DECISIONS diverge from reality, or a spec requirement has no
coverage; **medium** — a reproducible defect outside the acceptance items;
**low** — robustness, rule hygiene.

## Findings

### 1. [critical] The "cart cleared" notification is unreachable in the delivered scheduler
- `app/scheduler.py:142-143` — `loop` calls `run_once` (hold expiry)
  **before** `end_ended_sales` with the same `now`. `app/services/cart.py:129` —
  `expires_at = min(now + 10 min, ends_at)`, so at the moment `now >= ends_at`
  every `held` row already has `expires_at <= now`. `run_once` moves all
  such rows to `expired` (without a notification), and `end_ended_sales`
  (`app/scheduler.py:84-121`) finds no `held` rows at all. The `held → cleared`
  branch + `enqueue_cart_cleared` is dead code in production.
- Scenario: a buyer keeps a hold on a unit until the end of the sale and does not
  pay. On the `ends_at` tick: reservation `expired`, order `cancelled`,
  `notifications` — empty. Confirmed twice: by a script (E1:
  `expired=1 ended=1 cart_cleared_notifications=0`, including a hold taken 5
  minutes before the end) and on the real compose stack (E2E: row
  `3|4|expired`, the `notifications` table contains only two `order_paid`).
- The test `test_sale_end_clears_holds_and_notifies` (`tests/integration/test_sale_end.py:24`)
  calls `end_ended_sales` directly, bypassing `run_once`, which is why it is green.
  Spec item 9 ("owners get notified") is marked proven in README — wrong.
- Minimal fix: swap the call order in `loop` (first `end_ended_sales`, then
  `run_once`) **or** exclude from `run_once` the holds whose sale has already
  ended (`JOIN sales ... WHERE sales.ends_at > :now`), and add a test that runs
  exactly the `loop` sequence (`run_once` → `end_ended_sales`) at
  `now = ends_at` and asserts that `cart_cleared` is present.

### 2. [high] README does not name the model that wrote the code
- `README.md:10-12` — "the scaffold, plan and audit sessions used Claude Fable 5.1";
  README is silent about deepseek-v4-pro (all stages 0–8, `agent-sessions/2026-09-11-*.md:3`,
  `2026-09-12-stage-8-submission.md:3`), pointing to the directory instead.
  The spec ("What it was built with: which model") requires this in the project
  description.
- Fix: one sentence in README: implementation — deepseek-v4-pro via Claude Code
  on a non-Anthropic endpoint; audits/plan — Claude Fable 5.1.

### 3. [high] The promised stage 8 session export is missing
- `agent-sessions/2026-09-12-stage-8-submission.md:4-5` promises
  `2026-09-12-stage-8-submission.jsonl`; the file does not exist (the directory
  has four jsonl files, the last one is `2026-09-11-frontend-stage-7.jsonl`).
  Commits `5672f17`, `80fe49c`, `e495e22`, `934fcfe` (all 2026-09-12) are not
  covered by an export. The spec asks for a full export before submission.
- Fix: add the export, or state explicitly in the md that there is no export of
  this session and why.

### 4. [high] The app's INFO logs are not printed under uvicorn: the mail stub "sends nothing", LOG_LEVEL is dead for the server
- `app/main.py:33` sets the level on the `app` logger, but nobody adds a
  handler; uvicorn configures only its own loggers. `app/email_stub.py:10`
  (`logger.info`) and `app/scheduler.py:146` go to `lastResort`, which prints
  only WARNING and above (which is why `logger.exception` in `scheduler.py:153`
  is visible, while INFO is not).
  On the clone stack after two payments: `email to` in the backend log — 0 lines,
  `expired ... holds` — 0 lines; the only `app.*` line comes from seed, which
  calls `basicConfig` itself (`app/seed.py:73`).
- Consequence: the only observable trace of the "email" is `sent_at` in the
  table; the "stub writes to the log" contract (DECISIONS "Email via an outbox")
  does not hold; `LOG_LEVEL` changes the behaviour of seed only
  (config-hygiene "Declared means wired").
- Fix: `logging.basicConfig(level=settings.log_level)` in `create_app` (or
  uvicorn's `log_config` with a handler for `app`), plus a test that
  `send_email` produces a record in `caplog`.

### 5. [medium] The idempotency key lives in `sessionStorage`: payment is impossible from a second tab
- `frontend/src/stores/cart.ts:24,33,52` — `checkouts` are stored per tab. In a
  second tab (or after a browser restart) a new key is generated for the same
  reservation, `POST /orders` hits `uq_orders_reservation_id`
  (`app/services/orders.py:89-106`) → 409 "reservation already has an order",
  `orderId` stays `null`, every click repeats the 409. The buyer can neither pay
  nor "try again" from that tab — contradicts spec requirement 11 (two tabs).
  The backend's response to this request is already pinned by the existing test
  `test_create_order_same_reservation_different_key_409`
  (`tests/integration/test_orders.py:115`); the frontend half of the chain is
  from reading `cart.ts:84-106`, not reproduced in a browser.
- A key cannot return someone else's result: the key is unique together with
  `user_id`, and a repeat with a different reservation → 409 (`orders.py:58-59`).
  Verified.
- Fix: on a 409 when creating an order, look the order up by `reservation_id`
  in `GET /me/orders` and continue payment with it; or return `order_id` in
  `GET /me/cart`.

### 6. [medium] argon2 blocks the event loop on every login/registration
- `app/services/auth.py:28,32` — synchronous `pwdlib` inside `async def`
  (`app/routers/auth.py:41,59`). Measured: hash 51 ms, verify 39 ms (E5). At
  the moment a sale starts, a wave of logins stalls all SSE streams and
  `reserve` one after another. python-core [MUST] "no blocking I/O in async paths".
- Fix: `await asyncio.to_thread(verify_password, ...)` /
  `to_thread(hash_password, ...)`.

### 7. [medium] Three defaults for one webhook secret
- `app/config.py:27` (`"dev-secret"`), `paystub/main.py:107` (`"dev-secret"`,
  via `os.environ.get`, bypassing Settings — config-hygiene [MUST]),
  `tests/integration/test_payments.py:114,227` (`b"dev-secret"` hardcoded).
  If a developer has `PAYSTUB_WEBHOOK_SECRET` exported in their shell, both
  webhook tests fail. `.env.example:20` keeps the value empty and generates it —
  a fourth truth.
- Fix: tests sign with `Settings().paystub_webhook_secret` (or build the app
  with an explicit `Settings(paystub_webhook_secret=...)`); in paystub — the
  same pydantic-settings object or a required variable with no default.

### 8. [medium] `VITE_API_URL` from the root `.env` is read by nobody
- `frontend/vite.config.ts:16` reads `process.env.VITE_API_URL`; Vite loads
  `.env` files from `frontend/`, not from the root, and does not populate
  `process.env` from them. `frontend/Dockerfile` does not pass the variable. The
  value in `.env.example:37` and the README line (`README.md:55`) are a knob with
  no effect; it works only because the default happens to match.
- Fix: `loadEnv(mode, path.resolve(__dirname, '..'))` in `vite.config.ts`, or
  remove the variable from `.env.example`/README and `NON_SETTINGS_KEYS`
  (`tests/unit/test_config_env_contract.py:13`).

### 9. [medium] The seed race on `sales.title` is reachable
- `app/seed.py:48-52` — SELECT, then INSERT with no constraint. DECISIONS
  (`DECISIONS.md:29-31`) declares the race unreachable "in a single-process
  topology". Two concurrent `seed_demo_sale` calls produce two live demo sales
  (E6: `demo sales=2`). Reachable: `make seed` by hand while the container is
  starting (the entrypoint seeds too) and `docker compose up --scale backend=2`.
- Fix: `pg_advisory_xact_lock(hashtext('demo-seed'))` before the check, or a
  partial UNIQUE on `title WHERE status='active'`.

### 10. [low] A webhook with a non-ASCII signature is an unhandled `TypeError` (500)
- `app/routers/payments.py:93` — `hmac.compare_digest(str, str)` raises
  `TypeError: comparing strings with non-ASCII characters` (E3, header
  `X-Webhook-Signature: café`). Response 500 instead of 401; the stub sees a 500
  as "not delivered" and retries. Without a signature — 401, correct. There is
  no replay protection, but a replay is harmless: `UPDATE payments ... WHERE status='pending'`
  (`app/services/payments.py:115-126`) — a repeated delivery and a repeated
  `resolve` are no-ops; verified (E3, test `test_order_email_sent_exactly_once`).
- Fix: compare bytes: `compare_digest(signature.encode("latin-1", "replace"), expected.encode())`.

### 11. [low] The loser of a concurrent double click gets the wrong message
- `app/services/payments.py:79-87` — after a zero-row `UPDATE` the branch reads
  `reservation.status` from memory (it is still `held`), so the second
  concurrent `/pay` gets 409 "reservation is not held" instead of "payment already in
  progress" (E2: `200 pending | 409 reservation is not held`, the stub called
  once, `payments=1`). The frontend shows this text to the buyer.
- Fix: after a zero-row UPDATE, re-read the status with `SELECT status ... WHERE id`.

### 12. [low] `/api/events` without authentication broadcasts the statuses of all orders
- `app/routers/events.py:15-24`, `app/services/payments.py:207-209` — any
  unauthenticated client sees `order_status {order_id, status}` for all
  orders and `sale_status`. The leak is small (id and status), but the
  transactional-web module speaks of "clients of the affected scope".
- Fix: `Depends(current_user)` on `/events`, or filter by `user_id` in the
  payload on the SSE generator side.

### 13. [low] Login timing reveals whether an email exists
- `app/services/auth.py:98` — for an unknown email argon2 is not called: ~1 ms
  versus ~40 ms. Practical value is low: `POST /auth/register`
  (`app/routers/auth.py:43-46`) already answers 409 for a taken email.
- Fix (if needed): verify a dummy hash when `user is None`.

### 14. [low] Mismatches between test names and assertions
- `tests/integration/test_payments.py:164` `test_hung_payment_keeps_stock`
  checks only `payments.status == pending`; "the item is not returned and not
  sold twice" is actually proven by
  `test_payment_started_before_expiry_completes_after` (`available == 0`,
  `paying` after `run_once`).
- `test_double_pay_same_key_one_order` and `test_double_pay_calls_paystub_once`
  (`test_orders.py:59`, `test_payments.py:122`) — sequential requests, not a
  "double click". The concurrent case is proven only by this audit (E2).
  Fix: `asyncio.gather` of two requests in both tests.
- `tests/integration/test_realtime.py:135-136` — polling with `asyncio.sleep(0.01)`
  with `noqa` and a reason; acceptable, I record it as the only deviation from
  testing [MUST] "no sleep".

### 15. [low] README: a stale phrase about Secure cookies
- `README.md:50` — "(later: Secure cookies)", while `app/routers/auth.py:72`
  already sets `secure=app_env != "dev"`. Verified on the clone: in dev the
  cookie is `HttpOnly; SameSite=lax` without `Secure`.

### 16. [low, process] DECISIONS entries lag behind the commits that made the decision
- AGENTS.md requires an entry "in the same change as the decision". The hold
  clamp to `ends_at` was adopted in `c9e337c` (11.09 13:13), the outbox and
  zeroing the stock in `dd16428`/`d12a1d1` (14:11/14:14); both DECISIONS entries
  appeared only in `9571e31` (15:05, "fix: compose wiring…"). Cancelling the
  order on a decline after the end of the sale (`2dae4ad`) got no entry at all
  (see the DECISIONS list below). A reviewer checking gradual progress by entry
  dates will see the mismatch.

### Checked, no defect found (steps 3–4, for the record)
- Broadcast happens only after `commit` in all five places: `cart.py:139-144`,
  `cart.py:190-191`, `scheduler.py:58-60`, `scheduler.py:122-126`,
  `payments.py:206-208`. The outbox row is written in the same transaction as
  the transition (`payments.py:164-166` before the `commit` at 206;
  `scheduler.py:119-122`).
- A webhook arriving before the `/pay` commit is impossible by construction:
  `provider_ref` is generated by the backend and committed (`payments.py:89-99`)
  before the HTTP call (`routers/payments.py:66`); the stub learns the reference
  only from that call.
- A double "pay" before the first one commits: `UPDATE reservations ... WHERE
  status='held'` is serialised by the row lock; the loser gets 0 rows (E2). The
  partial UNIQUE `uq_payments_order_pending` is the second line of defence; it
  never comes to that.
- Payment at the `expires_at` boundary concurrently with a tick: `start_payment`
  (`expires_at > :now`) and `run_once` (`FOR UPDATE SKIP LOCKED`, `expires_at <= :now`)
  compete for one row; a tick that did not get the lock skips the row and sees
  `paying` on the next tick. A request whose transaction began before expiry
  can beat a tick that began after it — acceptable.
- End of the sale while `paying`: `available = 0`, the reservation stays;
  a later `approved` → `sold`/`paid`/email (E7), a later `declined` → `cleared`,
  order `cancelled`, `cart_cleared`, the unit is not returned (E8, documented in
  the plan). `available` thereby loses a unit for good — deliberately.
- `PostgresClock.now(db)` = `transaction_timestamp()` (E4: two reads 0.5 s apart
  give the same value; after `commit` — a fresh one). In `/pay` the second
  `clock.now(db)` comes after a commit, so it is fresh; in the scheduler the
  tick's `now` is reused by three functions after intermediate commits —
  consistent and harmless. The only risk is future code that keeps using the
  old `now` after a `commit`; check for it in review.
- Email twice: `send_pending` (`notifications.py:57-64`) sends, then commits
  `sent_at`; a crash in between gives a repeat (at-most-one duplicate, allowed
  by the module). There will be no second outbox row — UNIQUE `(kind, entity_id)`.
- Cookie: HttpOnly, SameSite=Lax, Secure outside dev, lifetime =
  `SESSION_TTL_DAYS`; all mutations are POST/DELETE with JSON, Lax does not send
  the cookie on a cross-site POST.
  Logs: tokens, passwords and card numbers do not reach the logs (the card
  number is only in the body of the POST to the stub; the stub does not log).
  Secrets: `.env` is not in git, no generated values found in `agent-sessions/`
  (grep for the current values and for the pattern `=[0-9a-f]{40,}`),
  `.env.example` contains no secrets, compose requires the variables via
  `${VAR:?}`.
- Step 5, mechanics: `datetime.now/utcnow/func.now/time.time/date.today` in
  `app/` — 0 (the test `test_no_local_time` exists); `os.environ` outside
  Settings — only `paystub/main.py:107` (item 7) and conftest; `time.sleep` in
  tests — 0; `except Exception` — only `app/scheduler.py:152`, with logging
  (justified, but it is a [MUST] exception with no documented escape in the
  module); `relationship`/lazy-load — not used, all relations go through
  explicit SELECTs; no business logic in routers; `fetch` only in
  `src/api/client.ts`; `skip/xfail` — 0; every Settings field has a consumer
  (except item 4 — `log_level` for the server); `.env.example` ↔ Settings is
  checked by a test.
  All components are `<script setup lang="ts">`, `v-for` with id keys, state
  in Pinia.

## State table (audit version)

| # | Item | Test | Real DB / commits / connections | Time | Assessment | Why it differs from README |
|---|---|---|---|---|---|---|
| 1 | Not before the start; opens for everyone at the moment of the start | `test_reserve_before_start_rejected`, `test_reserve_at_start_allowed` | yes, real commits, one client | `FrozenClock` exactly on the boundary | **partially proven** | Matches. Not proven: (a) simultaneity on the server — a test with two connections at `now == starts_at` (both 201) and at `starts_at − 1 µs` (both 409) would close this; (b) on the client the start is determined by its own ticking timer from `server_now` with an offset that includes half the RTT, and the server sends no "started" event. Fully provable only after adding `sale_status: started` from the scheduler and a store test for it. |
| 2 | Stock changes for everyone without a refresh | `test_stock_event_reaches_second_client`, `test_sse_smoke_real_server` | yes; two broadcaster subscribers + one real uvicorn/SSE client | frozen | proven | The two subscribers are at the broadcaster level, not two HTTP clients; E2E on the clone: 7 events received by an external `curl`. |
| 3 | The last unit goes to one of two | `test_last_unit_two_buyers_one_wins` | yes; two `SessionFactory()`, `gather`, real commits | frozen | proven | — |
| 4 | 10-minute hold, return, everyone sees it | `test_hold_expires_returns_stock`, `test_hold_expiry_broadcasts` | yes; `run_once` directly | frozen | proven | `loop` is not run by any test (see item 1). |
| 5 | A payment started before expiry completes after it | `test_payment_started_before_expiry_completes_after` | yes; separate sessions per step | frozen | proven | — |
| 6 | Hung: order pending, not sold twice, settled later | `test_hung_payment_keeps_stock`, `test_hung_payment_resolves_via_webhook`, `test_paystub_timeout_keeps_order_pending` | yes | frozen | proven | "keeps_stock" does not check the stock; the stock is proven by the test from row 5. Confirmed by E2E (`…9995` → resolve → paid). |
| 7 | Double "pay" — one order, one charge | `test_double_pay_same_key_one_order`, `test_double_pay_calls_paystub_once` | yes, but the requests are sequential | frozen | proven (concurrency — only by the audit) | E2: `gather` of two `POST /orders` → one order; of two `POST /pay` → one attempt, the stub called once. The tests should be made concurrent. |
| 8 | One email per order | `test_order_email_sent_exactly_once` | yes; webhook replay → the same single row | frozen | proven (at the outbox level) | "Exactly one" holds for the outbox; sending — at-most-one duplicate on a crash between send and commit; in production the send is not visible in the log (item 4). |
| 9 | End: unsold stock withdrawn, carts cleared, owners notified | `test_sale_end_clears_holds_and_notifies` | yes, but `end_ended_sales` is called bypassing `run_once` | frozen | **not proven** (the notification does not happen) | Withdrawal (`available = 0`) and cart clearing work; the owner notification is unreachable in the delivered `loop` — item 1, confirmed on the clone. |
| T11 | Two tabs in sync | row 2 + `useRealtime.test.ts` + `sales.test.ts` "two successive stock events" | yes / jsdom | — | proven, with a caveat | Storefront and account — yes. Paying for the same reservation from a second tab — 409 forever (item 5). |

## DECISIONS entries that diverge from the code

1. **2026-09-11 "Email via an outbox; sale end zeroes stock"** (`DECISIONS.md:52-57`):
   "clears its held reservations" — in production holds go to `expired` via
   `run_once`, not to `cleared`, and without a notification (item 1). "the
   scheduler sends them through the email stub" — the send is not observable in
   the log (item 4).
2. **2026-09-10 "Declined payment keeps the reservation and the order"**
   (`DECISIONS.md:119-122`): after `ends_at` the code moves the reservation to
   `cleared` and **cancels the order** with a notification
   (`app/services/payments.py:185-203`, commit `2dae4ad`). The plan
   (`docs/plan.md:217-218`) promised "the order does not change". There is no
   entry that would supersede this: `2dae4ad` did not touch DECISIONS.
3. **2026-09-11 "Sale times are absolute, in the shop's IANA zone"**
   (`DECISIONS.md:80-85`): "renders the times back in that zone" — the API
   returns `starts_at`/`ends_at` in UTC (`...Z`) plus a separate `timezone` field
   (`app/routers/sales.py:75-77`; E2E: `"starts_at":"2026-09-12T05:49:24Z","timezone":"UTC"`).
4. **2026-09-12 "Demo sale is seeded, keyed by title…"** (`DECISIONS.md:23-33`):
   "the check-then-act race is unreachable" — it is reachable (item 9, E6).
5. **2026-09-12 "Clock reads now() through the request's own session"**:
   implemented as written; the "transaction start time" semantics confirmed (E4).
6. **2026-09-10 "No default secrets in compose"**: true for compose; but
   `Settings.paystub_webhook_secret = "dev-secret"` and the same default in
   paystub mean that outside compose the backend and the stub start with a known
   secret (item 7). The entry about the shop's demo password calls this out; the
   one about the webhook secret does not.

The remaining entries (SSE instead of WebSocket and its revision to native
`EventSource`; one process; paystub as an HTTP service with a webhook; sessions
without SECRET_KEY; argon2id; one active hold per buyer; payment attempts with a
single pending; a time guard in the transition; "hung" = pending and a timeout;
no reconciliation; a single time source; fire-late; the frontend coverage
threshold; AGENTS.md; rule modules; clamping the hold to `ends_at`; the shop's
demo account) match the code.

## README "Next steps" versus what the audit found unproven

`README.md:96-105` lists LISTEN/NOTIFY and a worker, an auto-timeout for hung
payments with reconciliation, pagination. Not mentioned:

- Defects, not a "next iteration" (they don't belong in Next steps, they need
  fixing): the notification at the end of the sale (item 1); payment from a
  second tab (item 5); invisible INFO logs and the mail stub (item 4).
- Deliberate limitations that would be more honest to record in State/Next steps:
  the unit irrecoverably lost on a decline after `ends_at` (`available` is
  already 0); the absence of a server-side "sale started" event — the only way to
  make row 1 fully provable; `/api/events` without authorisation (item 12);
  blocking argon2 (item 6).

## Verdict: **fix-first**

Blocking: item 1 (acceptance item 9 does not hold, while README says proven),
items 2 and 3 (mandatory spec deliverables: the model in README, the export of
the last session), item 4 (the declared contract of the mail stub is not
observable). After them — item 5 (two tabs at payment) and item 6.

## Step 1: what was run and with what result

Audit machine: macOS, Docker Desktop, uv 0.12.x, Node 24.2.0 via nvm.

| Command | Result |
|---|---|
| `docker compose up -d db` | `lastunit-db-1` was already up and healthy. |
| `make check` (first run, Node **16.20.2** in the shell) | **FAIL** on `frontend-check`: `eslint . → TypeError: configs.findLastIndex is not a function` (`@vue/eslint-config-typescript`). Cause — the environment: `frontend/.nvmrc` = 24, README Prerequisites requires Node 24. Not a repository defect. The backend half passed: 75 passed, coverage 94.66 % (threshold 85). |
| `make check` (Node 24.2.0) | **PASS**. Backend: ruff, format, mypy, 75 passed, 3 DeprecationWarning (starlette/httpx, not the project's), coverage 94.66 %. Frontend: lint, prettier, vue-tsc, 45 passed (7 files), coverage lines 95.62 % / statements 87.38 % (threshold 80). |
| `make test-integration` | **PASS**: 59 passed, 11.4 s. |
| `make ci` | **PASS**: check + `frontend-build` + `uv audit` (0 vulnerabilities in 36 packages) + `npm audit` (0). |
| `make docker-build` | **PASS**: three images built. |
| `git clone <repo> <scratch>/clone` → `make install` | **PASS**, 4.2 s (`make env` created `.env` with generated secrets; `uv sync`; `npm ci`). |
| `make up` in the clone | **PASS**, 10.8 s, four containers. Deviation from the literal README: on this machine ports 5432/8000/8080 are taken by unrelated containers, so a `docker-compose.override.yml` was added to the clone that changes **only the host ports** (15432/18000/18001/18080); the internal layout (`backend:8000`, `paystub:8001`, `db:5432`, nginx proxy) is untouched. |
| `curl /api/health` (via backend) | `200 {"status":"ok"}` — after ~6 s (migrations + seed in the entrypoint). |
| `curl /api/sales` (via backend and via nginx :80) | `200`, one demo sale `Demo flash sale`, 5 units, `phase: upcoming`, starting one minute after seed. |
| `curl /` (nginx) | `200`, SPA. |
| `curl -N /api/events` (via backend and via nginx, 3 s) | `200 text/event-stream`, chunked, `X-Accel-Buffering: no`; no body within 3 s (ping every 15 s) — the connection stays open. |
| `curl :8001/docs` (paystub) | `200`. |
| `POST /api/auth/login` (`shop@example.com`/`shop-password`) | `200`, `Set-Cookie: session=…; HttpOnly; Max-Age=2592000; Path=/; SameSite=lax` (no `Secure` — dev). |
| E2E on the clone (scripted scenario): a 90 s sale, 3 units; b1 reserve→order→pay `…0000`; b2 pay `…9995` → `check` (pending) → `resolve` on the stub; b3 reserve without paying; wait for the end | b1: `approved` synchronously, the webhook from the stub accepted (`POST /api/payments/webhook 200`), order `paid`. b2: `pending`, `check` → `pending`, `resolve approved` → order `paid`. Stats before the end: `available 0, sold 2, in_cart 1`. After the end: `phase ended`, `available 0`, `in_cart 0`; reservations `sold, sold, expired`; notifications: two `order_paid` (`sent = t`), **no `cart_cleared`**; SSE at the external client: 4 `stock_changed`, 2 `order_status`, 1 `sale_status ended`. |
| `docker compose down -v` in the clone | done, stack and volume removed. |
| Experiments E1–E8 (script outside the repo, DB `app_test`) | E1 tick order → `notifications=0` (item 1). E2 concurrent `/orders` and `/pay` → 1 order, 1 attempt, 1 stub call (item 11). E3 webhook: no signature 401; non-ASCII signature → `TypeError` (item 10). E4 `now()` = transaction start. E5 argon2 51/39 ms (item 6). E6 two seeds → 2 sales (item 9). E7 approve after the end → `sold/paid`, email. E8 pay after `ends_at` before the tick → `HoldExpiredError`; decline after the end → `cleared/cancelled`, unit not returned. |

## Questions for the human

1. Item 9: when fixing item 1 — should holds that expire exactly at the moment
   the sale ends count as "cleared at the end" (email) or as "expired"
   (no email)? Right now `expires_at` is clamped to `ends_at`, and these two
   events are indistinguishable; the answer decides whether to change the order
   in `loop` or the condition in `run_once`.
2. A decline after `ends_at` cancels the order (`2dae4ad`), contrary to the plan
   and DECISIONS 2026-09-10. Is this a deliberate decision that needs a
   superseding entry, or a rollback to "the order does not change"?
3. `DECISIONS` "renders the times back in that zone" — should the API return
   times in the shop's zone (and then the code changes), or should the entry be
   corrected?
4. A public `/api/events` with the statuses of all orders — acceptable for a
   demo, or close it behind authorisation?
5. The unit lost on a decline after the end of the sale (`available` is already
   0) — is it recorded as accepted behaviour in README "State"/"Next steps"?
6. The stage 8 session export (`2026-09-12-stage-8-submission.jsonl`): will it be
   added, or should the md state that it does not exist?
7. Commit history: pairs 0–3 s apart (`7752cdf`/`597c7a0`/`e617d25`,
   `d91b529`/`a6b7bf6`, `4c869d8`/`5f699ac`, `28c24c8`/`8044d03`) were created in
   one pass; a reviewer checking "progress of the work over time" will see this.
   Leave it, or explain it in `agent-sessions/`?
8. The webhook secret with the default value `dev-secret` in two places — keep
   it as a demo convenience (then record it in DECISIONS next to the demo
   password) or remove the default?

## Security review

A separate `/security-review` run (Claude Code, Claude Fable 5.1) over the same
range `efdaea8..HEAD`, after the fix-first commits (`ab0eaa3`). Method: three
parallel searches by area (auth/API routers; payments, webhook, paystub,
scheduler, infrastructure; frontend and SSE), then a separate false-positive
filter for each candidate with a threshold of 8/10. Tests, `*.md` and
`agent-sessions/` are out of scope; DoS, rate limiting and secrets stored on disk
are excluded by the skill's rules.

**Result: no HIGH or MEDIUM findings.** Six Low-level candidates, each discarded
by the filter with a score of 2/10.

| Candidate | Location | Why discarded |
|---|---|---|
| Paystub is published on the host; `POST /payments` with an arbitrary `callback_url` and `/resolve` without authentication | `docker-compose.yml:46-47`, `paystub/main.py:125-156` | A stub by design (README, DECISIONS). Forging a webhook requires a pending `provider_ref` (128 bits, returned only to the shop role); the result is the same as entering card `…0000`. |
| The SSE stream is not closed on logout; `user_id` is fixed at connection time | `app/routers/events.py:27-32`, `frontend/src/composables/useRealtime.ts` | The payload is only `order_id` and `status`; the stores do not render it but refetch with the current cookie. The scenario requires a shared browser and a user switch in one tab without a reload. |
| `APP_ENV` defaults to `dev`: cookie without `Secure`, `/docs` open | `app/config.py:17`, `app/routers/auth.py:72` | The env variable is a trusted value; the stack has no TLS termination; the switch is documented in README and `.env.example`. |
| Register returns 409 for a taken email | `app/routers/auth.py:40-45` | Standard registration behaviour; email verification is impossible with a mail stub; the leak is one bit. |
| Password without `min_length` | `app/routers/auth.py:19-26` | A hardening gap; no third-party attack path without brute force (excluded by the rules). |
| httpx logs the URL with `provider_ref` on `check` | `app/main.py:37`, `app/paystub_client.py:49` | Logging URLs is considered safe; the ref is already visible to the shop role via `/shop/sales/{id}/stats`. |

### Checked, no defect found
- **Sessions.** `secrets.token_urlsafe(32)`, SHA-256 hash in the DB with UNIQUE,
  `expires_at` checked against the DB clock, a new token on every login, logout
  deletes the row. Cookie `httponly` + `samesite=lax`; there is no CORS
  middleware, so cross-site POST/DELETE requests carry no cookie.
- **Authorisation.** Every mutating and private route goes through
  `current_user` or `require_shop`; `register` hard-assigns the BUYER role.
  All id parameters (reservation, order) are scoped by `user_id` in the service
  query; the idempotency key is protected by `UNIQUE(user_id, idempotency_key)`.
  `/api/events` resolves the cookie with the same `user_for_token`, and
  `order_status` is delivered only to the owner. A side effect of this scoping is
  functional, not security: the shop dashboard subscribed to `order_status` and
  stopped seeing payments after the scoping (there is no stock event here —
  `available` already drops at the hold stage). Fixed with a separate unscoped
  `sale_stats` event, see DECISIONS and
  `test_payment_result_broadcasts_sale_stats_to_everyone`.
- **Payments.** Webhook: HMAC-SHA256 over the raw body, `compare_digest` on bytes.
  Replay is a no-op via the guarded `UPDATE … WHERE status='pending'` and the
  partial unique index on `(order_id) WHERE status='pending'`. `amount_minor` is
  taken from `sale.price_minor`, not from the client. The card number is neither
  stored nor logged. `callback_url` and the stub URL come only from `Settings`.
- **Injections.** `text()` only with literals (`SELECT now()`, advisory lock);
  `ZoneInfo` rejects `..` and absolute paths; email is normalised and
  constrained by CHECK/UNIQUE. The frontend has no `v-html`/`innerHTML`; the only
  `:href` is a constant with `rel="noopener"`; the redirect after login is handled
  by vue-router as a same-origin path.
- **Secrets and build.** compose uses `${VAR:?}`, `.env.example` has no values,
  `.env` was never committed, `.dockerignore` excludes `.env*`,
  `loadEnv` with the default `VITE_` prefix, `sourcemap: false`, CI with
  `permissions: contents: read` and SHA pins, `npm ci --ignore-scripts`.
- **Seed and prod guard.** `seed_demo_sale` and the demo user are not created
  with `APP_ENV=prod`; `/docs` and `/openapi.json` are disabled in prod.

## Follow-up review (`/code-review`, Claude Opus 5)

A run over the same fix-first commits found two defects introduced by the
fixes themselves; both were closed in the same pass.

| Defect | Location | Fix |
|---|---|---|
| Scoping `order_status` by buyer cut the shop dashboard off from live sold/revenue/pending updates | `app/services/payments.py`, `frontend/src/stores/shop.ts` | An additional unscoped `sale_stats` event; the dashboard subscribes to it instead of `order_status`. Test: `test_payment_result_broadcasts_sale_stats_to_everyone` |
| Re-reading the hold in `start_payment` was a no-op: the session's identity map already held the stale object, and the race loser got "reservation is not held" | `app/services/payments.py` | `.execution_options(populate_existing=True)` on the re-reading `select`. Test: `test_start_payment_with_stale_hold_in_session_reports_pending_payment` (deterministic, not relying on the coroutine scheduler) |

Both tests were verified red before the fix.
