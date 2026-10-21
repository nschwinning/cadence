## Why

The three places that show a portfolio's money — the Dashboard, the Portfolios
list, and a session's detail — each mean something different by "P&L": the
Dashboard shows a range-scoped change in net asset value (ΔNAV), the Portfolios
list shows only cumulative gross realised P&L with no live valuation at all, and
the session detail header shows a realised-only "Total P&L" that duplicates (and
contradicts the framing of) the clean current-value / realised / unrealised
triple already in its KPI row. A user comparing the same portfolio across pages
sees inconsistent numbers, and the list and dashboard values are stale between
manual reloads. We want one definition of the money triple everywhere and a live
"current value" that refreshes on its own.

## What Changes

- **One P&L model everywhere.** Every surface presents the same triple — current
  portfolio value, realised P&L, and unrealised P&L — under one definition:
  - **Current value** is the live net asset value (cash plus open positions
    marked to current quotes, net of cumulative fees); point-in-time, not
    range-scoped.
  - **Realised P&L** is range-relative: the sum of closed-lot realised P&L for
    lots closed within the selected range. For the `Max` range (and for any view
    without a range picker) this reduces to the session's cumulative realised
    P&L.
  - **Unrealised P&L** is range-relative: the current live unrealised P&L on open
    positions minus the unrealised P&L captured in the range-start daily
    snapshot. For the `Max` range (and views without a range picker) this reduces
    to the current live unrealised P&L.
  - Fees remain a separate figure, and realised P&L stays **gross of fees**. The
    realised and unrealised figures are shown as two standard, independent
    numbers; they are deliberately **not** claimed to sum to ΔNAV over the range
    (fees and since-entry realised attribution make them non-additive), and the
    range return percentage remains the authoritative "how much the portfolio
    moved" metric.
- **Dashboard** per-session overview data gains range realised and range
  unrealised P&L; the hero tiles and portfolio leaderboard show the triple
  (current value, realised, unrealised) over the selected range alongside the
  existing range return and fees, recomputing when the range or session selection
  changes.
- **Portfolios list** rows gain a live current value plus realised and unrealised
  P&L (all-time / `Max` basis), replacing the lone cumulative "profit/loss"
  column; the list endpoint now marks each session to market, as the dashboard
  already does per request.
- **Session detail** keeps its existing live KPI triple and drops the redundant
  realised-only "Total P&L" header stat so the page states P&L once, consistently.
- **Live ~30s refresh.** The Dashboard overview, the Portfolios list, and the
  session detail KPIs auto-refresh their values on a recurring ~30-second
  interval while the view is visible (pausing when backgrounded), so the current
  value and P&L update without a manual reload. No new endpoint is required — the
  live valuation path already recomputes from current quotes per request.
- **Dashboard scope legibility (scoped section bands).** The Dashboard mixes
  range-scoped figures (realised/unrealised/return/fees, the equity curve, failed
  runs, recent activity, universe performers), a point-in-time live figure
  (current portfolio value/NAV), and current-composition figures (universe
  balance) with no visual cue for which is which. The dashboard is reorganised
  into three labelled scope bands — a **Portfolio value** band marked live
  (point-in-time), a **Performance** band that carries the range selector and an
  indication of the active range (all range-scoped figures live here), and a
  **Universe** band marked as current composition — so a user can tell at a glance
  why some numbers move with the range selector and others do not. Because the
  universe band mixes scopes, its best/worst performers carry their own range
  indication even though the balance summary beside them does not change with the
  range. This is layout/labelling only; it introduces no new data.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `dashboard`: the per-session overview performance data additionally carries
  range-relative realised and unrealised P&L for each session (with their
  definitions), so the client can render the money triple over the selected
  range.
- `ai-paper-trading`: a session returned to a client (listed or read singly)
  additionally includes its live current value, realised P&L, and unrealised
  P&L, marked to market at read time.
- `app-shell`: the Portfolios list rows show the live current-value / realised /
  unrealised triple; the Dashboard hero tiles and portfolio leaderboard show the
  range triple; the Dashboard is reorganised into labelled scope bands
  (point-in-time value / range-scoped performance / current-composition universe)
  that make each figure's scope legible, with the range selector docked in the
  performance band; and a new live auto-refresh behavior refreshes the Dashboard,
  the Portfolios list, and the session detail KPIs on a recurring interval.

## Impact

- **Backend** — `dashboard/service.py` (`_session_performance` / `SessionPerformance`
  gains range realised + unrealised, reusing `ClosedPosition.exit_date` filtering
  and the range-start `SessionValueSnapshot.positions` unrealised); the
  paper-trading session list/read path marks sessions to market via
  `compute_session_value` and carries the triple; `api/schemas.py`
  (`DashboardSessionPerformance`, the paper-trading session read) gains the new
  fields. No new migration (all inputs already recorded: `ClosedPosition`
  exit_date/realized_pnl, per-position unrealised in snapshots, the position
  ledger). No new endpoint.
- **Frontend** — `types/api.ts` mirrors the new fields; the Dashboard hero tiles,
  leaderboard, and aggregation helpers render the range triple; the Portfolios
  list gains current-value / realised / unrealised columns; the session detail
  header drops the duplicate "Total P&L"; the dashboard, list, and session-KPI
  query hooks gain a ~30s `refetchInterval` (per-hook, mirroring the existing
  order-sync polling pattern).
- **Not changed** — the daily EOD snapshot cron and the value-history chart; the
  Sharpe / benchmark / drawdown KPIs; the session-detail KPI definitions
  (already the live triple); fee accounting (realised stays gross of fees).
