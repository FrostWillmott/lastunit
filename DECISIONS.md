# Decisions

Append-only log of non-obvious choices — not a changelog of every commit.
Newest entry at the top. See `documentation.md` in the rules-library for the
convention. Don't edit past entries; if a decision is reversed, add a new one
that supersedes it.

<!--
## YYYY-MM-DD — <short title>
<One or two lines: the decision and why. Link related files/PRs if useful.>
-->

## 2026-09-11 — Hold expiry is clamped to the sale's end
A hold's `expires_at` is `min(now + 10 min, sale.ends_at)`, so it never outlives the
sale. Side effect: paying after the sale ended is indistinguishable from paying after
the hold lapsed (the hold lapses at or before the sale end), so the "sale has ended"
409 is dead code and both cases surface as "hold has expired".

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
`timestamptz` UTC, and renders the times back in that zone. This satisfies the
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
