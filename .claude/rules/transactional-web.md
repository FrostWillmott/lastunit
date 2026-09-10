# Transactional multi-user web apps

Apply to any client-server product where several users act on shared state at
the same time: booking, sales, voting, reminders, monitoring. Assumes
`python-core.md` and `backend-fastapi.md`. Rule levels are in `_LEVELS.md`.

This module covers the requirements that every such product shares and that
agents get wrong by default: two clients see the same thing live, the last unit
is sold once, a double click is one order, one email per event, time zones,
money, and a scheduler that survives a restart. None of it is framework-specific.

## Concurrency is settled in the database, not in Python  [MUST]
- Invariants ("one seat per booking", "stock ≥ 0", "one vote per user per idea")
  are constraints: `UNIQUE`, `CHECK`, exclusion constraints on ranges
  (`EXCLUDE USING gist (place WITH =, during WITH &&)`). Application checks are
  a UX nicety; the constraint is the guarantee.
- Read-modify-write on contended rows uses `SELECT ... FOR UPDATE` (or
  `FOR UPDATE SKIP LOCKED` for queues) inside one transaction, or an atomic
  `UPDATE ... WHERE stock > 0 RETURNING`. Never read in one query and write in
  another and hope.
- Concurrent edits of the same record use optimistic versioning: a `version`
  column, `UPDATE ... WHERE id=? AND version=?`, zero rows → 409 with the
  current version so the client can show "changed elsewhere". Silent
  last-write-wins is a defect.
- A test proves each invariant under contention: two coroutines/threads hit the
  same last unit, exactly one succeeds, the other gets the defined failure.
  This is the "provability" the task brief asks for — write it before the UI.

## Every mutating endpoint is idempotent  [MUST]
- Client-generated `Idempotency-Key` (UUID) on POSTs that create money-bearing
  or one-shot things (order, booking, vote, registration). Stored with the
  result; a repeat returns the stored result, never a second row.
- Event ingestion (telemetry, sales events, webhooks) dedupes on a natural key
  (`(device_id, ts)`, `(point_id, event_id)`) via `INSERT ... ON CONFLICT DO NOTHING`.
- State transitions are guarded: `UPDATE orders SET status='paid' WHERE id=? AND
  status='pending'`. Re-delivering "paid" twice is harmless by construction.

## Exactly-once side effects go through an outbox  [MUST]
- Email/notification is never sent inside the request handler. The handler
  writes a row to a `notifications` (outbox) table in the same transaction as
  the state change; a worker sends and marks it. Crash between commit and send
  → resent; crash after send before mark → at-most-one duplicate, which the
  dedupe key on `(entity_id, kind)` prevents from ever being enqueued twice.
- "One letter per incident/reminder/order" is a `UNIQUE` on the outbox, not a
  boolean flag on the entity.
- The mail provider is a stub (`app/email_stub.py` that appends to a table or
  log) by default; the outbox table is the observable contract and the thing
  tests assert on.

## Scheduled work survives restarts  [MUST]
- Due times are rows (`reminders.fire_at`, `checks.next_run_at`), not in-memory
  timers. The scheduler loop polls `WHERE fire_at <= now() AND fired_at IS NULL
  FOR UPDATE SKIP LOCKED`, so two workers never fire the same job.
- A job that runs longer than its interval is not started again in parallel:
  claim it (`running_since`) before running, release after.
- Decide and document in README what happens to jobs that came due while the
  server was down (fire late / skip and mark missed / show as gap). The task
  briefs ask for this explicitly.
- Jobs are cancelled by state, not by finding the timer: deactivating a note
  sets its reminders' `cancelled_at`; the loop ignores them.

## Live updates reach every open client  [MUST]
- Server pushes state changes (WebSocket or SSE) to all connected clients of
  the affected scope; clients never poll to stay current. Broadcast happens
  after commit, from the same place the outbox row is written, so UI and email
  never disagree about what happened.
- Multiple backend workers → a pub/sub channel (Postgres `LISTEN/NOTIFY` is
  enough for a demo; Redis if you already run it), not process-local sets.
- On reconnect the client refetches, then resumes the stream. "Once shown, not
  shown again after reload" is state on the server (`seen_at`), not in
  `localStorage`.
- A test opens two clients, mutates through one, asserts the other received
  the event. That test is the proof for "works with two tabs open".

## Time: store UTC, compute in the entity's zone  [MUST]
- Store `timestamptz` (UTC). Every user/point/device has an explicit IANA zone;
  "local day", "midnight", "quiet hours" are computed in that zone at query
  time with `zoneinfo`, never by adding an offset.
- Changing a user's zone changes display and future local-day boundaries; it
  never moves an already-scheduled absolute instant. A test covers a DST
  boundary and a zone change on the day of travel.
- Recurrence ("weekly until date") expands to concrete occurrences in the
  entity's zone; per-occurrence overrides are rows referencing the series.

## Money is integers or `Decimal`  [MUST]
- Store minor units as `BIGINT` (kopecks/cents) or `NUMERIC(…, 2)`; never
  `float`. Arithmetic in `Decimal` with an explicit rounding mode.
- Splitting an amount: allocate `floor` to each share, hand the remainder cents
  out by a stated, deterministic rule (e.g. to the earliest participant), and
  assert `sum(shares) == total` in a test. Document the rule in README.
- Tariff boundaries (day/night, paused/riding) are computed per minute across
  the boundary; a test crosses it.

## Stay fast at thousands of rows  [PREFER]
- List endpoints are paginated (keyset, not offset, once ordering is by time)
  and filter/search server-side over the whole set; the client never receives
  everything and filters locally.
- Indexes exist for every `WHERE`/`ORDER BY` a hot endpoint uses; the
  migration that adds the query adds the index.
- Aggregates over history (uptime %, revenue per window) are either indexed
  queries with bounded ranges or materialised incrementally; never a full scan
  per page load.

## What "provable" means for this module  [PREFER]
For each "expected behaviour" bullet in the task brief there is one named test
(`test_<entity>_<condition>_<expected>`), and README's "State" section is a
table of those bullets with the test name and pass/fail. Concurrency and
two-client bullets are integration tests against the real database, per
`testing.md`.
