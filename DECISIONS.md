# Decisions

Append-only log of non-obvious choices — not a changelog of every commit.
Newest entry at the top. See `documentation.md` in the rules-library for the
convention. Don't edit past entries; if a decision is reversed, add a new one
that supersedes it.

<!--
## YYYY-MM-DD — <short title>
<One or two lines: the decision and why. Link related files/PRs if useful.>
-->

## 2026-09-12 — The shop dashboard refetches on `sale_stats`, not `order_status`
Scoping `order_status` to the buyer who owns the order (a privacy fix) cut the shop
dashboard off: it subscribed to that event, and a settled payment fires no stock
event because `available` is decremented at reserve time, so sold/revenue/pending
stopped moving live. `apply_payment_result` now also publishes an unscoped
`sale_stats` carrying only `sale_id`. Rejected: unscoping `order_status` (leaks
order ids to every connection) and reusing `stock_changed` (it would lie about
stock and make every buyer's store refetch). A sale id is already public in the
sale list, so the broadcast reveals nothing new — the figures behind it still
need the shop-only stats endpoint.

## 2026-09-12 — Minimum password length applies only at registration
Registration enforces `min_length=8` through a `RegisterRequest` schema that
subclasses the shared `CredentialsRequest`; login keeps the unconstrained
schema so a too-short password on sign-in returns 401 (wrong credential)
rather than a 422 validation error. Length is a creation contract, not an
authentication check.

## 2026-09-12 — A decline after the sale end clears the reservation and cancels the order
Accepted in commit `2dae4ad`, recorded late. Once a sale has ended its
`available` is already 0, so a payment declined after `ends_at` has no unit to
return: the reservation is cleared (not `held`) and the order is cancelled with a
cart-cleared notice, mirroring the sale-end cleanup path. This supersedes the
2026-09-10 "Declined payment keeps the reservation and the order" entry, which
held only while the sale was still live.

## 2026-09-12 — Clock reads now() through the request's own session
`PostgresClock.now()` used to open a second pooled connection per call, so a
burst of authenticated requests (each pinning its request session's connection
for the uncommitted auth SELECT) could exhaust the pool and 500 right as a sale
opens. `now()` now takes an optional session and the request paths pass their
own `db`, so the clock read reuses the request's connection; the scheduler passes
its loop session, and the seed still opens its own. Semantically `now()` becomes
the request transaction's start time — fine for a demo and consistent within a
request. Tests inject `FrozenClock`, which ignores the session.

## 2026-09-12 — Demo sale is seeded, keyed by title, re-anchored when it ends
`make seed`/the entrypoint also create a demo sale (5 units, 99.00, Europe/Moscow)
starting a minute after the seed, so `make up` shows a live flash sale. It is
idempotent by `sales.title` and re-anchored: if the previous demo sale's window
has passed, a fresh one is created, so a later start still shows a live sale and
ended demo sales accumulate as terminal rows. Keying on the user-writable title
(no natural key, no UNIQUE constraint) is a deliberate demo-only simplification —
the check-then-act is serialized with a `pg_advisory_xact_lock`, so concurrent
seeds (a manual `make seed` during startup, or two scaled workers) can't create
two live demo sales, and the demo sale is not an application invariant worth a
migration. A shop creating a sale literally named "Demo flash sale" would suppress
re-seeding.

## 2026-09-11 — Realtime uses native EventSource, not VueUse useEventSource
`useEventSource` exposes only "latest value" refs (its `event`/`data` are shallowRefs),
so watching the event name drops two consecutive same-named events — two `stock_changed`
in a row deliver one callback. `useRealtime` therefore opens a native `EventSource` and
fans out via `addEventListener` (fires per event), relying on the browser's built-in
auto-reconnect and refetching on reopen. The "two tabs" acceptance bullet is proven by
the backend two-client integration test plus the frontend fan-out test and the
store-applies-two-events test — a store unit test that mocks the realtime composable
away does not by itself certify it.

## 2026-09-11 — Hold expiry is clamped to the sale's end
A hold's `expires_at` is `min(now + 10 min, sale.ends_at)`, so it never outlives the
sale. Side effect for the payment transition: paying after the sale ended is
indistinguishable from paying after the hold lapsed (the hold lapses at or before the
sale end), so both surface there as "hold has expired". The reserve path keeps its own
"sale has ended" 409 for a sale that ended before the scheduler swept it.

## 2026-09-11 — Email via an outbox; sale end zeroes stock
Order-paid and cart-cleared emails are `notifications` rows (UNIQUE kind+entity) written
in the same transaction as the state change; the scheduler sends them through the email
stub and marks `sent_at`. Ending a sale sets `available = 0` and clears its held
reservations (paying ones settle later), so the stats buckets (available/sold/in-cart)
do not sum to `quantity`.

## 2026-09-11 — Demo shop account: committed default password, seeded dev-only
`SEED_SHOP_EMAIL`/`SEED_SHOP_PASSWORD` default to `shop@example.com`/`shop-password`
so a reviewer can log straight into the shop screen without reading `.env`. The seed
runs only when `APP_ENV != "prod"` and uses an atomic upsert (`INSERT ... ON CONFLICT
(email) DO UPDATE`) so it is idempotent, normalizes the email, and upgrades a buyer
who registered the shop email first. This deliberately qualifies the earlier "no
default secrets" entry — the shop credential is a demo convenience, not a production
secret.

## 2026-09-11 — Domain schema: invariants live in constraints
The first migration creates users, sessions, sales, reservations, orders,
payments and notifications. Guarantees are schema constraints, not app checks:
`CHECK (available >= 0)`, `CHECK (available <= quantity)`, `CHECK (quantity > 0)`
and `CHECK (starts_at < ends_at)` on sales; a `CHECK` that every status/role
column holds an enum value (so a case-variant cannot slip past the partial
indexes); `CHECK (email = lower(email))`; partial UNIQUE `(sale_id, user_id)` on
reservations where `status IN ('held','paying')`; UNIQUE `(user_id, idempotency_key)`
on orders; partial UNIQUE `(order_id)` on payments where `status = 'pending'`;
UNIQUE `(kind, entity_id)` on notifications. Statuses are string enums in
`app/models/enums.py`; each transition is a guarded `UPDATE ... WHERE status = <from>`.

## 2026-09-11 — Sale times are absolute, in the shop's IANA zone
The shop creates a sale with a wall-clock start/end plus a `timezone` (IANA) column
on the sale; the backend parses the local time with `zoneinfo.ZoneInfo`, stores
`timestamptz` UTC, and returns them in UTC alongside the `timezone` field, for
the client to render in the shop's zone. This satisfies the
`transactional-web` [MUST] that a zone be explicit, without forcing a zone on
buyers — buyers only ever see a `server_now`-offset countdown.

## 2026-09-10 — SSE instead of WebSocket for live updates
Updates flow one way (server → browser), so `GET /api/events` over SSE with VueUse
`useEventSource` gives reconnect for free and needs no socket protocol of our own.

## 2026-09-10 — One uvicorn process; LISTEN/NOTIFY is the next iteration
API, scheduler (lifespan task) and broadcaster run in one process with an
in-memory fan-out; the demo has no second worker to justify pub/sub yet, and the
README "Next steps" names LISTEN/NOTIFY and a separate worker as the path to it.

## 2026-09-10 — Payment stub is a separate HTTP service with a webhook
`paystub/` runs as its own FastAPI service in compose and answers by webhook, so
the backend integrates a real HTTP contract (approve, decline, hang, resolve later)
instead of an in-process fake that could never be late.

## 2026-09-10 — Login and password with server-side sessions, no SECRET_KEY
Session token is `secrets.token_urlsafe(32)`; the DB stores its SHA-256, the cookie is
HttpOnly + SameSite=Lax, Secure outside dev. A random opaque token needs no signature,
so there is no `SECRET_KEY` to declare, rotate or leak.

## 2026-09-10 — Passwords hashed with argon2id via pwdlib
argon2id is the first recommendation of the OWASP Password Storage Cheat Sheet
(https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html);
`pwdlib` is the maintained wrapper, while `passlib` has had no release since 2020.

## 2026-09-10 — One active reservation per buyer and sale
Partial UNIQUE on `reservations(sale_id, user_id) WHERE status IN ('held','paying')`
keeps one buyer from holding the whole batch; the database enforces it, not a check.

## 2026-09-10 — One order per reservation; payments are attempts, one pending at a time
`orders.reservation_id UNIQUE` and a partial UNIQUE on `payments(order_id) WHERE
status='pending'` make a double click a constraint violation before any HTTP call.

## 2026-09-10 — Declined payment keeps the reservation and the order
A declined attempt returns the reservation to `held` with its original `expires_at`
and leaves the order `pending`; the buyer retries with a new attempt until the
hold expires, so a card typo does not cost the unit.

## 2026-09-10 — Payment after hold expiry is refused by the transition itself
`held → paying` is `UPDATE ... WHERE status='held' AND expires_at > :now AND :now < ends_at`;
zero rows → 409, so behaviour does not depend on when the scheduler last ran.

## 2026-09-10 — "Hung" means both a `pending` reply and an HTTP timeout
Both leave the attempt and the order `pending` with the unit held; the payment row is
committed before the call, so a timeout can never roll back a payment the stub accepted.

## 2026-09-10 — No automatic reconciliation with the payment stub
The stub retries an undelivered webhook, and the shop screen has a "check status"
button that asks the stub and applies the answer through the webhook handler; a
periodic poll would add a second resolver racing the webhook for no demo value.

## 2026-09-10 — One time source: Postgres, via a `Clock` and a `:now` parameter
Services take `now` from `SELECT now()` once per transaction and pass it to every
query; no `datetime.now()` in business logic, no `now()` inside SQL. Tests inject a
frozen clock, and all processes agree on the time.

## 2026-09-10 — Scheduled work that came due while the server was down fires late
On startup the poll loop processes everything with `fire_at <= now()`; a missed hold
expiry must still return the unit, and "skip and mark missed" would leave it held forever.

## 2026-09-10 — Frontend coverage threshold counts only stores and api
`coverage.include` in `vite.config.ts` is `src/stores/**` and `src/api/**` with the
reason in a comment: that is where state and the realtime proof live, while screens
are checked by lint and types and would only dilute the number.

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
