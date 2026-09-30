## Why

The session-detail KPI tiles report value, P&L, total return, Sharpe, and benchmark comparison, but give no view of downside risk or trade-level effectiveness. Two questions a paper-trader asks first — "how deep was the worst decline?" and "how often do my closed positions actually make money?" — are unanswerable today, even though the underlying data (daily value snapshots and closed positions with realized P&L) is already recorded.

## What Changes

- Add four compute-on-read KPIs to a session's KPI read, all derived from data already persisted (no new columns, no migration, no config):
  - **Maximum Drawdown %** — the largest peak-to-trough decline in portfolio value across the session's ordered daily value-snapshot series.
  - **Win Rate** — the fraction of the session's closed positions whose realized P&L is greater than zero.
  - **Average win / Average loss** — the mean realized P&L of profitable closed positions and, separately, of losing closed positions.
  - **Best trade / Worst trade** — the largest single winning and losing closed-position realized P&L.
- Each metric is nullable and reports absent when its inputs are insufficient: drawdown is absent with no value snapshots; the four trade-based metrics are absent with no closed positions (and average win / average loss are each absent when there are no winners / no losers respectively).
- Surface the new metrics as additional KPI tiles on the session-detail page only (not the multi-session comparison list).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ai-paper-trading`: the per-session KPI read gains maximum-drawdown, win-rate, average-win, average-loss, best-trade, and worst-trade figures, each computed on read from existing value-snapshot and closed-position data and reported as absent when inputs are insufficient.
- `app-shell`: the session-detail KPI tiles display the new drawdown and trade-effectiveness metrics.

## Impact

- Backend: `paper_trading/service.py` — extend `session_kpis()` and the `SessionKpis` dataclass with the six new figures (drawdown from the `SessionValueSnapshot.total_value` series; win-rate/avg/best/worst from `ClosedPosition.realized_pnl`). `api/schemas.py` — add nullable fields to `PaperTradingSessionKpisRead`.
- Frontend: `types/api.ts` — mirror the new fields on `PaperTradingSessionKpis`; `pages/paper-trading/PaperTradingSessionPage.tsx` — add `StatTile`s to `KpiRow`.
- Tests: backend KPI service + endpoint tests; frontend session-page test.
- No database migration, no new configuration, no change to how snapshots or closed positions are recorded.
