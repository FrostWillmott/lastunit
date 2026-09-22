---
name: verify
description: Build, launch and drive the flash-sale stack end to end to observe a change at its real surface (browser tabs, HTTP, SSE). The recipe from the 2026-09-12 runtime verification, re-run over HTTP on 2026-09-22 — ports, seed, flows, gotchas. Use before committing a change to app/, paystub/ or frontend/; not for docs- or tests-only diffs.
---

Verification is runtime observation: run the stack, drive the affected flow,
capture what you see. Do not run `make check` here; CI proves that.
Recorded run and report format: `docs/verification-2026-09-12.md`.

## Launch

Ports 8000/8080/5432 are often held by other projects on this machine
(`pacer-*`, `verbatim-*`). `make up` then dies with a raw docker bind error.
Remap host ports with an override; in-network wiring (`backend:8000`) is untouched.

Keep the override outside the tree (scratchpad or `mktemp -d`) so it can
never be committed.

```bash
make env                                   # .env with generated secrets, no-op if present
OV=$(mktemp -d)/ports.override.yml
cat > "$OV" <<'YAML'
services:
  db:
    ports: !override []
  backend:
    ports: !override ["18000:8000"]
  paystub:
    ports: !override ["18001:8001"]
  frontend:
    ports: !override ["18080:80"]
YAML
dc() { docker compose -f docker-compose.yml -f "$OV" "$@"; }   # a function, not a string variable: zsh does not word-split it
dc up --build -d
for i in $(seq 90); do curl -sf localhost:18000/api/health >/dev/null && break; sleep 1; done  # macOS has no `timeout`
```

Healthy in about 3 s after `up` on 2026-09-22. The backend entrypoint runs
`alembic upgrade head` and `python -m app.seed` before uvicorn, so the shop
user and a "Demo flash sale" exist once `/api/health` answers. Tear down with
`dc down -v` so the next run starts from an empty database.

App: `http://localhost:18080`. API: `http://localhost:18000/api`. Paystub:
`http://localhost:18001`. Shop login is `SEED_SHOP_EMAIL` / `SEED_SHOP_PASSWORD`
from `.env` (`set -a; . ./.env; set +a` loads them without printing).
`POST /api/auth/register` creates a buyer but does **not** start a session:
follow it with `POST /api/auth/login` into the same cookie jar.

## Handles

- **Browser**: two tabs on the same origin share the session cookie. Tab 1
  storefront, tab 2 storefront or shop dashboard. "Two tabs in sync" means both
  update with `performance.getEntriesByType("navigation").length === 1`.
- **curl** with a cookie jar for concurrency and as a third SSE client:

```bash
API=localhost:18000/api; H='content-type: application/json'
S=$(mktemp); curl -sc $S -H "$H" -d "{\"email\":\"$SEED_SHOP_EMAIL\",\"password\":\"$SEED_SHOP_PASSWORD\"}" $API/auth/login
# starts_at/ends_at are NAIVE wall-clock in `timezone`; a trailing Z is a 422. `date -v` is macOS; Linux: `date -d "-1 min"`
curl -sb $S -H "$H" -d "{\"title\":\"A\",\"price_minor\":1999,\"quantity\":1,\"timezone\":\"UTC\",
  \"starts_at\":\"$(date -u -v-1M +%FT%T)\",\"ends_at\":\"$(date -u -v+2H +%FT%T)\"}" $API/sales   # 201, id
J=$(mktemp); curl -s -H "$H" -d '{"email":"b1@example.com","password":"password123"}' $API/auth/register
curl -sc $J -H "$H" -d '{"email":"b1@example.com","password":"password123"}' $API/auth/login
curl -sb $J $API/sales                                        # id, available, phase, starts_at/ends_at
curl -sb $J -X POST $API/sales/<id>/reserve                   # 201 | 409 "sold out" | "sale has not started yet" | "already in cart"
curl -sb $J -H "$H" -H "Idempotency-Key: $(uuidgen)" \
     -d '{"reservation_id":<rid>}' $API/orders                # 201; same key again → same order, 201
curl -sb $J -H "$H" -d '{"card_number":"4000000000000000"}' \
     $API/orders/<oid>/pay                                    # {"status": approved|declined|pending}
curl -sN -b $J $API/events > $(mktemp) &  SSE=$!            # SSE client; kill $SSE when done
```

A background SSE listener makes a bare `wait` hang forever: `wait $PID` the
race you started, or kill the listener first. Cookie jars store the session as
a `#HttpOnly_` line, so `grep -v '^#'` hides it.

- **Paystub cards** (last four digits): `0000` approved, `0002` declined,
  `9995` pending (hangs). The reference is `payments.provider_ref` for the
  order. Resolve a hung payment (`outcome`: `approved` or `declined`), which
  also fires the webhook to the backend:
  `curl -H 'content-type: application/json' -d '{"outcome":"approved"}' localhost:18001/payments/<reference>/resolve`.
- **Time**: do not wait ten minutes. Edit rows through the db container and
  let the scheduler (1 s tick) pick them up:

```bash
psql() { dc exec -T db psql -U app -d app -tAc "$1"; }        # app = POSTGRES_USER/DB default in .env.example
psql "UPDATE reservations SET expires_at = now() - interval '1 minute' WHERE id = <rid>"
psql "UPDATE sales SET ends_at = now() - interval '1 minute' WHERE id = <id>"
psql "SELECT kind, entity_id FROM notifications"          # one row per (kind, entity_id)
```

## Flows worth driving

Each maps to a README "State" row; observe the surface named there.

1. Sale in the future: button `disabled` in both tabs, reserve → `409`. At
   `starts_at` the button enables without reload; note whether it refetched.
2. Reserve in tab 1 → tab 2 stock changes within ~0.5 s, no reload.
3. Last unit: two `reserve` calls in parallel (`&` + `wait`) → one `201`,
   one `409 sold out`, stock 1→0.
4. Expire a hold via SQL → status `expired`, stock returns, tabs update.
5. Hold in `paying` when it expires → status stays `paying`, unit stays with
   the buyer; late webhook → order `paid`, reservation `sold`. Replaying the
   same webhook is a no-op: still one row in `payments`.
6. Card `…9995` → order `pending`, stock unchanged; `resolve` → `paid`.
7. Double click "pay" in the UI → one `POST /orders`, one `POST /pay`
   (`read_network_requests`). Two parallel `POST /pay` → `409 payment already
   in progress` + `200`, one row in `payments`. Pay on a paid order →
   `409 reservation is not held`; another buyer's order → `404`.
8. `notifications` has one `order_paid` row per order and one `cart_cleared`
   per cleared hold; the paystub log shows one send even after decline → retry.
9. `ends_at` in the past → holds `cleared`, unsold removed, `cart_cleared`
   letters, phase `ended`.

Check `dc logs backend paystub` for tracebacks at the end. All nine passed over
HTTP on 2026-09-22 with these commands; the browser half (flows 1, 2, 7 in the
UI) was not re-driven that day because the Chrome extension was disconnected.

## Gotchas

- A background Chrome tab throttles the client timer, so the "Starts in" switch
  can lag there; the storefront refetches when the tab becomes visible again.
  The server-side `409` is exact regardless. Measure timing in the active tab.
- The shell defaults to Node 16; `make up` does not need Node, but any
  `npm`/`npx` here needs `~/.nvm/versions/node/v24.15.0/bin` on `PATH`.
- Browser automation may stop delivering synthetic key events mid-run. A form
  that "does not submit on Enter" is the tool, not the app: check for a
  `keydown` listener firing before recording a finding.

## Report

Same shape as the built-in protocol this file replaces. Verdict is one of
**PASS** (ran it, works at its surface), **FAIL** (ran it, does not, or claim
and diff disagree), **BLOCKED** (could not reach an observable state; say
where), **SKIP** (no runtime surface). Steps are things done to the running
app with the captured output; at least one step is a probe off the happy path
(wrong method, double submit, stale state, two sessions at once). Findings list
everything that made you pause, not only bugs. When in doubt, FAIL.
