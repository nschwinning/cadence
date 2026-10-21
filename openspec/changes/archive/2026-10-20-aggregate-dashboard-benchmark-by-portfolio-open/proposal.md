## Why

The Dashboard's combined-equity chart draws a benchmark line that does not aggregate across portfolios. The combined **equity** line sums every selected session and steps up as each new portfolio opens and injects its capital. The **benchmark** line does not: the backend ships each index's raw daily closes, and the client rebases a single index curve to the combined curve's *first* point. At that earliest date only the first-opened portfolio holds any capital (later portfolios contribute zero until they open), so the benchmark line represents only the first portfolio's capital invested in the index and never steps up when later portfolios open. The result is a benchmark that is systematically mis-scaled against the equity curve — effectively "the benchmark for one portfolio."

The correct comparison is the one a buy-and-hold investor would experience: at each portfolio's open date, invest that portfolio's opening capital into the benchmark and hold; sum those positions across all (selected) portfolios. That makes the benchmark line step up as each portfolio opens, exactly as the equity line does, so the two are directly comparable.

## What Changes

- The Dashboard benchmark line becomes an **aggregate dollar line per index**: for each catalog index, the line equals the sum over the selected sessions of a buy-and-hold of each session's contributed capital in that index, bought at each contribution's effective date and held. It steps up as each new portfolio opens (its opening capital is a contribution) and is **contribution-aware** (later capital increases are additional contributions). The per-index toggle is preserved — each index line measures every selected portfolio against that same index — with S&P 500 selected by default.
- The benchmark line is summed over exactly the **selected sessions**, so toggling a session off drops both the equity line and the benchmark line consistently, with no refetch (same no-refetch toggling the equity curve already has).
- The range-scoped overview endpoint additionally returns, per session, that session's **capital contributions** (opening capital at its start date plus any later capital-increase events, each an effective date and amount). The index price series it already returns is unchanged (raw closes), and continues to be shipped un-rebased so the client can aggregate per the current selection.
- The client stops rebasing a single index curve to the combined curve's start. Instead it builds each selected index's line by accumulating, across the selected sessions' contributions, units of the index bought at each contribution date, valued forward at the index's close — which is mathematically the sum of the per-session contribution-aware dollar overlays. The hover tooltip reports each drawn benchmark line's aggregated USD value.

Out of scope: no change to the per-session detail chart, its benchmark overlay, or the session KPI benchmark/excess-return figures; no new benchmark table, migration, catalog, or ingestion change; the benchmark catalog and which indexes exist are unchanged.

## Capabilities

### Modified Capabilities

- `dashboard`: the per-session overview data now includes each session's capital contributions (opening capital + later increases), and the benchmark index series is defined as the input the client aggregates into a per-portfolio buy-and-hold overlay summed across selected sessions, rather than a curve rebased once to the combined start.
- `app-shell`: the Dashboard combined-equity chart draws each selected benchmark line as the sum over the selected sessions of a buy-and-hold of each session's contributed capital in that index (stepping up as portfolios open), re-aggregating on session selection changes, instead of rebasing a single index curve to the combined curve's starting point.

## Impact

- Backend: `backend/src/cadence/dashboard/service.py` (`_session_performance` to include contributions; `_benchmark_overlays`/overview assembly), `backend/src/cadence/api/schemas.py` (`DashboardSessionPerformance` gains a contributions field). Reuses `backend/src/cadence/paper_trading/service.py::session_contributions` and `backend/src/cadence/paper_trading/benchmark.py` (`load_benchmark_series`, `close_on_or_before`). No migration.
- Frontend: `frontend/src/pages/dashboard/aggregate.ts` (replace `rebaseBenchmarkLine` with a per-session contribution-aware aggregate), `frontend/src/pages/dashboard/CombinedEquityChart.tsx` (plot the aggregated dollar lines; tooltip), `frontend/src/types/api.ts` (`DashboardSessionPerformance` contributions field), and the dashboard tests.
- No API route, backend model, or benchmark-ingestion change.
