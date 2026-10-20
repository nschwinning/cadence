## Why

The Dashboard's combined equity curve shows the summed value of the selected paper-trading sessions, but there is no baseline to judge that line against — a user cannot tell at a glance whether the portfolios are beating the market. Overlaying benchmark index lines (rebased to the same starting capital) turns the chart into a comparison, reusing the benchmark price data the app already ingests for per-session benchmarking.

## What Changes

- The dashboard overview endpoint additionally returns, for the selected range, a per-index **benchmark price series** (date + closing price) for each catalog index that has stored prices over the range, so the UI can draw comparison lines without a second request.
- The Dashboard combined equity curve renders selectable **benchmark index lines** overlaid on the summed-value line. Each index line is **rebased to the currently-visible combined curve's starting point** (its first date and value) — i.e. "the combined starting capital invested in that index" — so every line starts from the same dollar value as the portfolio line and stays in dollars (no percent/dollar toggle).
- The chart gains a **benchmark checkbox legend** listing all catalog indexes (S&P 500, Dow Jones, NYSE Composite, Nasdaq Composite, Nasdaq-100, Russell 2000, S&P 100, Wilshire 5000). Only **S&P 500 is checked by default**; the user toggles others on or off. Toggling an index adds or removes its line **without a new request**, mirroring the existing per-session selection toggle.
- An index with **no stored price series** over the range is still listed in the legend but draws **no line** (and its checkbox is disabled/inert) — never an error.
- The benchmark lines re-rebase whenever the selected set of sessions changes (which changes the visible combined curve's start), so the comparison always shares the visible line's starting capital.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `dashboard`: The range-scoped overview additionally returns benchmark price series for the range so the combined equity curve can be compared against market indexes. (Adds a new requirement; the per-session performance requirement is unchanged.)
- `app-shell`: The Dashboard combined equity curve renders selectable benchmark index lines rebased to the combined curve's start, with a benchmark checkbox legend defaulting to S&P 500 and tooltip/empty-state behavior extended to the benchmark lines. (Modifies the existing "Dashboard combined equity curve" requirement.)

## Impact

- **Backend**: `dashboard/service.py` (overview assembly — add benchmark price series, windowed to the range), `api/schemas.py` (new `DashboardBenchmarkSeries` + point schema on `DashboardOverview`, plus the parallel service dataclass). Reuses `paper_trading/benchmark.py::load_benchmark_series`, the `Benchmark` catalog in `paper_trading/constants.py`, and the `benchmark_prices` table — no new table, no migration.
- **Frontend**: `pages/dashboard/CombinedEquityChart.tsx` (benchmark line series in `buildCombinedOption`, benchmark checkbox legend, client-side rebasing to the combined curve's first point, benchmark selection state), `types/api.ts` (overview benchmark-series types), reuse of the existing `useBenchmarks` catalog hook and the chart palette. No new API client needed beyond the extended overview payload.
- **No** new dependencies, env vars, or migrations. Benchmark price ingestion already populates every catalog index.
