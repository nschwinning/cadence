## 1. Notification message builders

- [x] 1.1 Create `backend/src/cadence/strategy_bots/notifications.py` with a best-effort
  send guard mirroring `ai_portfolio/notifications.py::_notify_safely` (swallows notifier
  exceptions, no-op on a null/None notifier); verify a unit test proves a raising notifier
  does not propagate and a None notifier sends nothing.
- [x] 1.2 Add `_kill_switch_message(...)` building the drawdown kill-switch body (bot
  label, liquidated positions, realised P&L on the liquidation, "bot is now stopped");
  verify a unit test asserts the rendered text contains those elements.
- [x] 1.3 Add `_bot_summary_message(...)` building the evening per-bot summary mirroring
  the AI report figures — value today (±$, ±%), total return (±$, ±%),
  realized/unrealized/cash/fees, Sharpe, benchmark suffix, best/worst open position — plus
  a "Trades today: N" line; verify a unit test asserts each figure and the trade-count
  line are present and that an absent Sharpe/benchmark renders like the AI report.

## 2. Service computations (no schema change)

- [x] 2.1 Add `count_bot_trades_on(session, bot, day)` counting `BotTrade` rows for the
  session with `created_at` on the given date (snapshot/close timezone); verify a unit
  test shows trades on other dates are excluded and same-day trades counted.
- [x] 2.2 Add `get_previous_bot_value_snapshot(session, *, session_id, before)` (prior
  `BotValueSnapshot` before a date) and a daily-P&L computation (diff vs prior total_value,
  baseline fallback to allocated_capital on day one, guard non-positive baseline);
  verify a unit test covers the normal diff, the day-one fallback, and the guarded percent.
- [x] 2.3 Add a `sharpe_ratio: float | None` field to the `BotKpis` dataclass and compute
  it inside `bot_session_kpis` by building the daily fractional-return series from
  consecutive `BotValueSnapshot.total_value` diffs and calling
  `paper_trading.service.sharpe_ratio`; verify a unit test returns `None` below the minimum
  observation count and a finite value above it.
- [x] 2.4 Add `sharpe_ratio: float | None` to the `BotKpisRead` schema in
  `api/schemas.py`; verify the bot KPI endpoint test shows the field is serialized
  (value when available, `null` otherwise).

## 3. Wire the kill-switch notification into the tick

- [x] 3.1 Add an optional `notifier` parameter (default `None`) to `run_tick` and
  `_tick_session` in `strategy_bots/service.py`, and send `_kill_switch_message` via the
  best-effort guard at the point the drawdown kill-switch sets `status = STOPPED`; verify
  a unit test with a recording notifier shows exactly one push on a trip, with the
  liquidation details and STOPPED.
- [x] 3.2 Verify (unit test) that a tick which does **not** trip the kill-switch sends no
  push, and that a None notifier and a raising notifier both leave the session liquidated
  + stopped without failing the tick.
- [x] 3.3 Add the notifier dependency to the `POST /api/v1/bots/tick` route in
  `api/routers/bots.py` and pass it to `run_tick`; verify the route still returns its
  existing `TickResult` shape (existing route test green, extended to assert the notifier
  is threaded).

## 4. Wire the evening summary into the snapshot job

- [x] 4.1 Add an optional `notifier` parameter (default `None`) to `run_bot_snapshots`
  and, for each session it snapshots, build and send `_bot_summary_message` (one push per
  bot, no roll-up) via the best-effort guard, assembling figures from `BotKpis`, the daily
  P&L (2.2), Sharpe (2.3), the benchmark comparison, best/worst position, and the day's
  trade count (2.1); verify a unit test with a recording notifier asserts one push per
  active bot carrying the mirrored figures and the correct "trades today" count.
- [x] 4.2 Verify (unit test) that a None notifier and a raising notifier both leave all
  value snapshots recorded without failing the snapshot job.
- [x] 4.3 Add the notifier dependency to the `POST /api/v1/bots/snapshot-daily` route in
  `api/routers/bots.py` and pass it to `run_bot_snapshots`; verify the route still returns
  its existing `BotSnapshotResponse` shape (existing route test green, extended to assert
  the notifier is threaded).

## 5. Frontend Sharpe tile on the bot detail page

- [x] 5.1 Add `sharpe_ratio: number | null` to the bot KPI type in
  `frontend/src/types/api.ts`; verify `tsc` typechecks.
- [x] 5.2 Render a Sharpe ratio KPI tile in `frontend/src/pages/bots/BotSessionPage.tsx`
  with a "not yet available" state + brief hint when the value is null (mirroring the AI
  session page's Sharpe tile); verify a Vitest in `BotSessionPage.test.tsx` asserts the
  numeric tile when a value is present and the not-yet-available state when it is null.

## 6. Verify gates

- [x] 6.1 Run `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run
  pytest` and verify all green.
- [x] 6.2 Run `cd frontend && npm run test && npm run build` and verify all green.
- [x] 6.3 Run `openspec validate add-strategy-bot-notifications --strict` and verify it
  passes.
