## Why

Strategy bots are tracked and traded like AI paper-trading sessions but, unlike AI
sessions, they send **no notifications at all**. When a bot's drawdown kill-switch
liquidates every position and stops the bot — a terminal, money-losing event — the
user learns nothing until they next open the app. And where every AI portfolio gets
an evening daily-P&L push, bots get silence. The user has asked for both: a push when
the kill-switch fires, and an evening per-bot summary carrying "the same figures as for
the AI portfolios plus the number of trades from the day."

## What Changes

- **Drawdown kill-switch notification**: when the intraday tick trips a session's
  whole-session drawdown kill-switch (liquidating all open positions and stopping the
  session), the system sends one Pushover notification naming the bot, the positions it
  liquidated, the realised P&L on the liquidation, and that the bot is now stopped.
- **Evening per-bot summary notification**: the daily bot snapshot job sends one push
  per active bot mirroring the AI daily report — value and daily P&L (± amount, ±%),
  total return (± amount, ±%), realized / unrealized P&L, cash, fees, Sharpe, a
  benchmark comparison, and the best/worst open position — **plus the number of trades
  the bot executed that day** (distinct from lifetime total trades).
- Both notifications are **best-effort and silent when Pushover is unconfigured**: a
  no-op notifier sends nothing, and a notifier failure never fails the tick or the
  snapshot job (mirroring the AI subsystem's `_notify_safely` convention).
- A `Notifier` is threaded into the bot tick path (`run_tick` and the `POST
  /api/v1/bots/tick` route) and the bot snapshot path (`run_bot_snapshots` and the
  `POST /api/v1/bots/snapshot-daily` route).
- **Sharpe parity on the bot detail page**: the bot detail page shows no Sharpe today.
  So the notification does not surface a figure that is absent from the bot's own page,
  `sharpe_ratio` is added to the bot KPIs (`BotKpis` / `BotKpisRead`), computed from the
  session's daily value-snapshot series, and a Sharpe KPI tile is added to the bot detail
  page (with a "not yet available" state until enough history, mirroring the AI page).
- A bot daily-P&L figure is **computed** from the session's existing value-snapshot
  series and ledger — no new columns, no migration.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `strategy-bots`: the "Optional take-profit, stop-loss, and drawdown kill-switch"
  requirement gains behavior that the tick sends a kill-switch notification when it
  liquidates and stops a session; the "Bot value snapshots and performance KPIs"
  requirement gains behavior that the per-session KPIs include a Sharpe ratio computed
  from the snapshot series, and that the daily snapshot job sends a per-bot daily-P&L
  summary notification including the day's trade count. Both notifications are best-effort
  and silent when the notifier is unconfigured.
- `app-shell`: a new requirement adds a Sharpe KPI tile to the bot session-detail page
  (with a "not yet available" state until the session has enough history), so the page
  shows the same Sharpe figure the evening notification reports.

## Impact

- **Backend**: `backend/src/cadence/strategy_bots/service.py` (thread `Notifier` into
  `run_tick`/`_tick_session` and `run_bot_snapshots`; fire the kill-switch push where a
  session is stopped; build and send the per-bot evening summary; add a "trades on day"
  count query and a bot Sharpe/daily-P&L computation reusing
  `paper_trading.service.sharpe_ratio`). New `backend/src/cadence/strategy_bots/
  notifications.py` (message builders + a best-effort send guard, paralleling
  `ai_portfolio/notifications.py`). `backend/src/cadence/api/routers/bots.py` (add a
  notifier dependency to the tick and snapshot-daily routes).
- **Bot KPIs + frontend**: `BotKpis` and `BotKpisRead` gain a `sharpe_ratio: float | None`
  field computed in `bot_session_kpis` (reusing `paper_trading.service.sharpe_ratio` over
  the session's snapshot series); `frontend/src/types/api.ts` mirrors it and
  `frontend/src/pages/bots/BotSessionPage.tsx` renders a Sharpe tile with a not-yet-
  available state.
- **APIs**: `POST /api/v1/bots/tick` and `POST /api/v1/bots/snapshot-daily` keep their
  contracts (notifications are a side effect). The bot KPI read gains one nullable
  `sharpe_ratio` field (additive, backward-compatible).
- **Notifications**: Pushover via the existing `Notifier` only; no new channel. A manual
  call to `POST /api/v1/bots/tick` may also emit the kill-switch push, since bots use a
  single tick endpoint for both cron and manual invocation.
- **No migration, no DB schema change.** The frontend change is limited to the bot detail
  page's Sharpe tile. Tick/snapshot schedules and market-hours gating are unchanged.
