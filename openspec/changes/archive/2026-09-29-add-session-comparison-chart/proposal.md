## Why

Users run several paper-trading sessions at once (different risk profiles, asset scopes, strategies) and today can only inspect performance one session at a time on the detail page. There is no way to see all sessions on one chart and tell at a glance which is performing best. A single comparison chart on the paper-trading list page turns a pile of independent experiments into a head-to-head leaderboard over time.

## What Changes

- Add a **multi-session performance-comparison chart** to the top of the paper-trading sessions list page. It overlays one line per session across a shared time axis.
- The chart includes **every non-archived session** (active, paused, stopped) — the same set as the default session list (`include_archived=false`). Archived sessions are excluded.
- Provide a **%/$ toggle** above the chart to switch the y-axis metric:
  - **Return %** (default): each session's line is the cumulative total-return percentage `(total_value − allocated_capital) / allocated_capital` at each snapshot, so sessions with different allocated capital and start dates compare fairly — the highest line is the best performer.
  - **Value ($)**: each session's line is its absolute total portfolio value in USD.
- Add a **new backend comparison read** that returns, in one call, each included session's label, allocated capital, and ordered value-history points (`{snapshot_date, total_value}`), so the frontend makes a single request instead of fanning out N per-session value-history calls.
- Render with a **new dependency-free inline-SVG multi-line chart component** mirroring the existing single-session `SessionValueChart` pattern (shared y-scale, non-scaling stroke, insufficient-data placeholder), with a **legend** mapping each color to its session label. Sessions with fewer than two snapshots appear in the legend but are not plotted.
- The existing **single-session value chart on the detail page is unchanged.**

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ai-paper-trading`: add a new requirement for a multi-session comparison value-history read (one response carrying each non-archived session's label, allocated capital, and ordered snapshot points).
- `app-shell`: add a new requirement for the paper-trading list-page comparison chart, including the %/$ metric toggle, the per-session legend, and the insufficient-data behavior.

## Impact

- **Backend**: new comparison read in `paper_trading/service.py` (reuses existing snapshot queries and the session list filter), a new response schema in `api/schemas.py`, and a new `GET` endpoint under `/api/v1/paper-trading` in `routers/paper_trading.py`.
- **Frontend**: new typed client fn + TanStack Query hook + types in `api/paperTrading.ts` / `types/api.ts`; a new comparison-chart component (inline SVG, reuses the shared `Panel` and `lib/format.ts`); wired into `pages/paper-trading/PaperTradingPage.tsx`.
- **No database/migration changes** — reads existing `session_value_snapshots` and `paper_trading_sessions`.
- No changes to the single-session detail chart, KPIs, or cron/snapshot jobs.
