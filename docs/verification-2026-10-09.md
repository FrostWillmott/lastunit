# Runtime verification (2026-10-09)

A repeat of the [2026-09-12 run](verification-2026-09-12.md) after the
post-submission changes to running code:

- the payment stub's callback allow-list (`faf0378`);
- SQLAlchemy 2.1 (`ca7b393`, `app/services/cart.py`);
- `@vueuse/core` 15, which changed the timer behind the storefront countdown and
  the cart's hold timer (`040694b`);
- uvicorn, Python/npm patch releases and base-image bumps.

The stack was built from `docker-compose.yml` at `85d0717`, and the nine
"Expected behaviour" bullets (`docs/acceptance.md`) plus the "two tabs" bullet
were checked through HTTP and the browser. As before, the project's tests were
not part of this run; CI covers them.

Tool: Claude Code (CLI), Claude Opus 5.5, following `.claude/skills/verify/`.

## How we checked

- Host ports were remapped to 18000/18001/18080 with a compose override kept
  outside the tree, and the database port was not published, because 5432 on
  this machine is held by another project's container.
- `curl` with cookie jars for every bullet, for the races, and as an SSE client.
- Browser: two tabs on the same origin with a buyer session, for the timers
  changed by `040694b`, two-tab sync, hold expiry and the double click on "Pay".
- Hold expiry and the end of a sale were reached by editing `expires_at` and
  `ends_at` in the database; the scheduler ran normally with a 1 s tick.

## Results per bullet

| # | Expected behaviour | What we observed | Result |
|---|---|---|---|
| 1 | Cannot buy before the start; at the start it opens for everyone | Server: `409 sale has not started yet`. Browser: "Starts in" ticked once a second before the window went to the background (54 changes in 53 s), button `disabled`; it enabled without a reload | done, with a caveat (finding 1) |
| 2 | Stock changes for everyone without a page refresh | Reserve in tab 1 → tab 2 went from "3 of 3" to "2 of 3", `navigations = 1` | done |
| 3 | The last unit cannot be sold to two buyers | Two simultaneous reserves: one `201`, one `409 sold out`, stock 1→0. The winner reserving again: `409 already in cart` | done |
| 4 | Hold of 10 min, return to the storefront, visible immediately | `expires_at` in the past → `expired`, stock returned, SSE `stock_changed`; in the browser tab 2 went from "4 of 5" back to "5 of 5", no reload. The cart's "Held for" timer ticked (9:42 → 9:38 over ~3 s) | done |
| 5 | A payment started before expiry completes | Hold expired while `paying`: status stayed `paying`, unit not returned. `resolve` → order `paid`, reservation `sold`; resolving again left one row in `payments` and one `order_paid` | done |
| 6 | The stub "hung" — the order waits, the item is neither returned nor sold twice | Card `…9995` → `pending` at once, order `pending`, stock unchanged at 0; `resolve` → `paid` | done |
| 7 | Double click on "pay" — one order, one charge | Browser double click → exactly one `POST /orders` (201) and one `POST /pay` (200). Same `Idempotency-Key` twice → the same order. Two simultaneous `POST /pay` → `409 payment already in progress` + `200`, one row in `payments`. Paying a paid order → `409`; another buyer's order → `404` | done |
| 8 | One email per order | `order_paid` 4 rows for 4 orders; decline → retry gave payments `declined, approved` and still one email | done |
| 9 | At the end: carts are cleared, unsold stock is withdrawn, owners are notified | Hold → `cleared`, one `cart_cleared`, available 0, phase `ended`, SSE `sale_status ended`; reserve afterwards → `409 sale has ended` | done |
| — | Two tabs stay in sync | Both tabs: `navigations = 1` for the whole run | done |

Payment stub allow-list: a payment with `callback_url` on `169.254.169.254` →
`422 callback_url host not allowed`; webhooks to `backend` were delivered
throughout bullets 5–8.

The `backend` and `paystub` logs for the whole run had no errors and no
tracebacks; neither browser tab logged a console error.

## Findings

### 1. [caveat] The start switch in an active tab was not timed
The automated Chrome window went to the background a minute into the run and
stayed there (`visibilityState: "hidden"` in both tabs), so Chrome throttled
timers to about once a minute. The storefront button enabled at 07:33:35.5 for a
boundary of 07:32:34, a 61 s lag. This is the background-tab behaviour already
described in README and in finding 1 of the 2026-09-12 run, not a regression.
The server-side `409` before the start is exact regardless. The 1 Hz cadence
under `@vueuse/core` 15 was observed before throttling began (07:31:13–07:32:06).

### 2. [tool] Clicks were dispatched through the DOM
With the window hidden, synthetic mouse clicks did not reach the page (no
request was sent). Buttons were pressed with `button.click()`, which runs the
app's own handlers but not a real pointer. The double click on "Pay" was two
synchronous `click()` calls, so the second arrived before any re-render: a
stricter test of the guard than a human double click.

### 3. [tool] A click in the same task as the input event hits a disabled button
The first "Pay" attempt sent nothing: the script set the card number and
clicked in one go, before Vue re-rendered the button as enabled. Clicking after
the render worked. Recorded so the next run does not report it as a defect.
