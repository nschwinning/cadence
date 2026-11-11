## Context

`POST /bots/tick` (cron, every 5 min 09:00–16:55 ET on weekdays) calls `service.run_tick`, which
now reconciles orders, processes each bot in its own commit, counts `failed` bots and returns a
`TickResult` — but nothing is persisted: the outcome only reaches the cron sidecar's curl and the
log. A tick that crashes outright (as on 2026-11-10) returns 500 and leaves no trace in the DB.
The dashboard overview (`dashboard.service.get_dashboard_overview`) already knows `market_open`.
The Admin account query (`useAdminAccount`) already feeds the Broker account tile and carries the
positions comparison and unresolved orders.

## Goals / Non-Goals

**Goals:** persist tick outcomes (7-day retention) and per-bot failure state; expose tick health
in the overview; a dashboard Health section; a failure banner on the bot detail page.

**Non-Goals:** push notifications; AI-rebalance/orchestrator failure surfacing (already covered
elsewhere); per-bot failure history beyond "latest + consecutive count".

## Decisions

1. **`bot_tick_runs` table** (`BotTickRun`): `id`, `ran_at` (tz, indexed), `market_open`,
   `processed`, `skipped`, `failed`, `reconciled`, `flattened`, `error` (text, null),
   `created_at`. One row per tick request. *Alternative:* a single "last tick" row — rejected:
   staleness needs the time of the last row only, but a short history (7 days) makes failures
   reviewable and costs ~550 rows/week.
2. **Recording in the router, not the service.** `POST /bots/tick` wraps `run_tick` + capital
   settlement: on success it records the outcome through the request session and commits with it;
   on an exception it records a failed outcome (`error = str(exc)[:500]`, counts unknown → 0)
   through an **independent** `SessionLocal()` session (the request session is rolled back), then
   re-raises so the cron still sees a 500. Recording errors are logged and swallowed.
3. **Per-bot failure columns** on `bot_sessions`: `last_failure_at` (tz, null),
   `last_failure_error` (text, null), `consecutive_failures` (int, default 0, server default 0).
   In `run_tick`'s per-bot `except` branch, after `session.rollback()`, the bot is re-loaded and
   the three fields updated and committed (best-effort, own try). When `_tick_session` returns
   `True` (processed), the fields are cleared in the same unit before commit; a skipped bot (no
   fresh data) is untouched. Stopped bots failing to flatten use the same path.
4. **Settings**: `BOT_TICK_RUN_RETENTION_DAYS = 7`, `BOT_TICK_STALE_MINUTES = 15` in `config.py`
   (defaults; no env var needed). Pruning is added to `run_bot_snapshots` next to
   `_prune_value_points`.
5. **Overview `tick_health`** (`dashboard.service`): latest `BotTickRun`; `stale = market_open and
   (no run or now − ran_at > BOT_TICK_STALE_MINUTES)`; `failing_bots` = non-archived bots with
   `consecutive_failures > 0`, ordered by most failures, with `bot_display_name`. Added to the
   `DashboardOverview` dataclass and schema as a range-independent field.
6. **Frontend**: `components/dashboard/HealthSection.tsx` takes `tickHealth` from the overview and
   reads `useAdminAccount` for consistency counts (`positions` by status: orphan, shortfall, short;
   `unresolved_orders.length`). The dashboard band becomes **"Account & health"** with the Broker
   account tile and the Health card side by side (`lg:grid-cols-2`). Bot detail: a red banner at the
   top of `BotSessionPage` from the new `BotSession` fields.

7. **Explicit rejections end the lease** (`OrderGateway` → `journal.record_submitted(...,
   expire_lease=True)` for `OrderError`): Alpaca returns an error for an order it refused, so no
   order exists; the next tick's reconciliation closes the row and the bot retries — and fails
   again, keeping `consecutive_failures` climbing instead of resetting on a "blocked" tick.
   Ambiguous failures (timeouts, connection drops) keep the lease.

## Risks / Trade-offs

- A cron that stops entirely (sidecar down) leaves no rows → covered by staleness while the market
  is open; outside market hours nothing is expected anyway.
- Error messages could in principle echo request details; broker errors carry Alpaca's message
  only (no keys), and messages are truncated.
- The Health card makes the dashboard depend on the Admin query for the consistency line; if the
  broker is unreachable that line says so and the tick part still renders.

## Migration Plan

Alembic migration adds `bot_tick_runs` and the three `bot_sessions` columns (`consecutive_failures`
with server default 0). Verify upgrade/downgrade on a scratch DB. Deploy with
`docker compose up -d --build`.

## Open Questions

None.
