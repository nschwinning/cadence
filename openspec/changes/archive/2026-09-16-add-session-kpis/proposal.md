## Why

The paper-trading session detail page shows allocated capital, schedule, cumulative realised P&L, and last-run time — but not how the session is doing *right now*. A user cannot see the portfolio's current market value, how much of the P&L is still unrealised (open positions marked to market), the overall return on capital, or any risk-adjusted measure of performance. These are the first questions someone asks when watching a strategy run. All the underlying data already exists (live valuation via the broker, the daily value-snapshot series); it is simply not exposed as headline KPIs.

## What Changes

- Add a **live session KPI endpoint** (`GET /api/v1/paper-trading/sessions/{id}/kpis`) that, on each load, marks the session's open positions to market through the broker and returns five figures:
  - **Current portfolio value** — live net asset value (cash + positions at current quotes).
  - **Realised P&L** — cumulative realised profit/loss (already tracked on the session).
  - **Unrealised P&L** — live mark-to-market gain/loss on open positions.
  - **Total return** — the overall gain/loss versus allocated capital, as both an absolute money amount and a percentage.
  - **Sharpe ratio** — annualised risk-adjusted return of the session's actual daily net-asset-value series; **nullable**, reported as "not yet available" until the session has accumulated enough daily history to be meaningful.
- Surface **unrealised P&L as a top-level figure** on the internal session valuation (today it is only reachable inside the per-position breakdown).
- Add a **pure Sharpe-ratio helper** computed from the session's ordered daily returns (mean/stdev annualised by √252, risk-free rate defaulting to 0), returning nothing below a minimum number of daily returns or when volatility is zero.
- Add a **KPI tile row** to the paper-trading session detail page rendering the five figures, with P&L and return coloured by sign and the Sharpe tile showing "Not yet available" with a hint while it is null.

No new persistence, no schema migration, and no external price-history fetching: the Sharpe input is the session's existing daily value snapshots.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `ai-paper-trading`: Adds a requirement for a live session KPI summary — current value, realised P&L, unrealised P&L, total return, and a Sharpe ratio computed from the session's actual daily NAV series (gated on a minimum history), served by marking open positions to market on demand.
- `app-shell`: Extends the paper-trading session view requirement so the session detail page presents these KPIs as headline tiles, colouring gains/losses and showing an unavailable state for Sharpe until enough history exists.

## Impact

- **Backend:** `paper_trading/service.py` (add top-level `unrealized_pnl` to the session valuation; add a pure Sharpe helper reading the daily-return series; add a `session_kpis` service function), `paper_trading/constants.py` (`SHARPE_TRADING_DAYS_PER_YEAR`, `SHARPE_MIN_RETURNS`, risk-free default), `api/schemas.py` (`PaperTradingSessionKpisRead`), `api/routers/paper_trading.py` (new `GET …/kpis` endpoint injecting the broker; unknown id → 404).
- **Frontend:** `pages/paper-trading/PaperTradingSessionPage.tsx` (KPI tile row), `api/paperTrading.ts` (`useSessionKpis` hook + query key), `types/api.ts` (`PaperTradingSessionKpis`), `lib/format.ts` (shared `formatCurrency`/`formatPercent`), reusing the existing `StatTile` component.
- **No** database migration, no new dependencies, no changes to order execution or the daily-rebalancing cron.
