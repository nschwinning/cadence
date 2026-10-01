## Why

The Dashboard today is a thin set of static counts (universe size, portfolio count, active sessions, recent trades). It does not answer the questions a daily-driver check-in actually asks: _How are my portfolios doing right now? Over the last week? Is the automation healthy? Is my universe balanced, and what's moving?_ Every performance view currently lives behind a per-session page, so there is no single place to see the whole system at a glance or to compare portfolios against each other over a chosen horizon.

This change rebuilds the Dashboard into that single overview, driven by one global broker-style range selector so every panel answers for the same time horizon.

## What Changes

- **Global range selector** (`1D / 1W / 1M / YTD / 1Y / Max`) pinned at the top of the Dashboard; the selected range drives every section below. Aggregation is over **active** paper-trading sessions only.
- **Hero performance tiles** (range-relative, respect the portfolio selection): total current value, P&L $ over the range, money-weighted return % over the range, and fees paid within the range — aggregated across the selected active sessions from existing value snapshots.
- **Combined equity curve**: a single summed $-value line of the *selected* portfolios on a common date axis (carry-forward; a session contributes 0 before its first snapshot), windowed to the range. A checkbox/legend of active sessions (all selected by default) lets the user select/deselect portfolios; the **selection filters the whole Dashboard** (tiles + leaderboard recompute client-side, no refetch per toggle). Empty state when none selected.
- **Portfolio leaderboard**: active sessions sorted by return % over the range (best first), with value, P&L $, return %, and fees columns; each row links to its session detail. Honors the global range and the portfolio selection.
- **Automation panel**: last rebalance run (status, relative time, link to its run), in-flight indicator, failed-run count within the range, and the next run approximated from the fixed cron slots (noting it ignores market holidays).
- **Recent activity feed**: AI runs (build / rebalance / close) across sessions within the range, newest first, capped, each linking to its run.
- **Universe section**: a range-independent **balance summary** (eligible/ineligible split, sectors covered, top-sector concentration %, top-category share) and **best/worst performers** — the top and bottom tracked assets by market return over the range.
- **New aggregated overview endpoint** (`GET /api/v1/dashboard/overview`) scoped to a range, returning per-session performance series, automation summary, recent activity, universe balance, and universe performers. The existing lean `GET /api/v1/dashboard/metrics` is left unchanged.
- **Price-history ingestion** (new): a stored daily-close table, a provider batch fetch, backfill on asset-add, and a daily append that piggybacks the existing rebalance cron — the only way to serve market return over `1Y`/`Max` ranges, which on-demand fetching cannot. This is a **deliberate move of the documented "price-history ingestion is out of scope" line**, made because the universe-performers feature cannot exist without stored history.

## Capabilities

### New Capabilities
- `price-history`: ingest and store daily close prices per asset (backfill on add, daily append via the existing cron trigger), and compute a per-asset market return over a selected range from the stored series.

### Modified Capabilities
- `dashboard`: add a range-scoped aggregated **overview** (per-session performance series, automation summary, recent activity, universe balance, and universe performers), alongside the existing metrics endpoint. Introduces the shared range semantics (`1D/1W/1M/YTD/1Y/Max`, money-weighted aggregation over active sessions).
- `app-shell`: rebuild the Dashboard view — global range selector plus the hero tiles, selectable combined equity curve, portfolio leaderboard, automation panel, recent activity feed, and universe section.

## Impact

- **Backend**: new `price_history` capability package (models + service + ingestion) and one Alembic migration adding the `price_history` table; a new `MarketDataProvider` batch daily-close method (real + stub); the rebalance cron path also triggers daily price ingestion; a new `GET /api/v1/dashboard/overview` endpoint + schemas in `api/schemas.py`; new dashboard service aggregates reusing `session_kpis` / `compute_session_value` / `list_value_history` / `list_ai_runs`.
- **Frontend**: Dashboard page rebuilt with a global range-selector control, new typed client for the overview endpoint, dependency-free inline-SVG equity curve, leaderboard table, automation/activity/universe panels, and `types/api.ts` additions. Co-located Vitest tests.
- **Scope line**: formally supersedes the "price-history ingestion out of scope" note for this feature; backtesting and technical indicators remain out of scope.
