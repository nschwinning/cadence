## 1. Backend — benchmark price series on the overview

- [x] 1.1 Add a `DashboardBenchmarkPricePoint` (`date`, `price`) and `DashboardBenchmarkSeries` (`benchmark_id`, `name`, `points`) to the dashboard service dataclasses, and a matching overview-level field (e.g. `benchmark_series`) on the overview result; verify mypy passes.
- [x] 1.2 Add the parallel Pydantic schemas to `api/schemas.py` and the new field on `DashboardOverview`, keeping the service dataclass and schema in lockstep; verify `uv run mypy src/cadence` passes.
- [x] 1.3 In the overview assembly (`dashboard/service.py`), build `benchmark_series` by iterating the `Benchmark` catalog, loading each index's stored series via `load_benchmark_series`, windowing it to the same range bounds used for the per-session value series, and resolving each index's display name from the benchmark catalog helper; an index with no points over the range yields an entry with an empty `points` list (never omitted, never raising).
- [x] 1.4 Add/extend a backend test asserting the overview returns one benchmark-series entry per catalog benchmark, each windowed to the range, with an empty-series index represented (not omitted) and no error; include the empty-system case. Verify `uv run pytest` passes for the dashboard overview tests.

## 2. Backend — verification gate

- [x] 2.1 Run `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` and verify all green.

## 3. Frontend — types and rebasing

- [x] 3.1 Mirror the new overview benchmark-series schema in `types/api.ts` (`DashboardBenchmarkSeries` + price point) and add the field to the overview type; verify `npm run -s typecheck` passes.
- [x] 3.2 Add a pure rebasing helper that, given a benchmark price series and the combined curve's first `[date, value]`, returns a rebased `[date, value]` line (anchor to the index's first price at/after the combined start; value = `V0 × price(t) / price(anchor)`; empty line when the index has no price at/after the start). Verify a unit test covers the normal case, the anchor-at/after-start case, and the no-data case.

## 4. Frontend — benchmark lines on the chart

- [x] 4.1 Add benchmark selection state (`Set<benchmarkId>`) to `CombinedEquityChart.tsx`, initialized to only S&P 500 selected, and a benchmark checkbox legend listing every catalog benchmark (names from the series/`useBenchmarks`); a benchmark whose series has no points over the range renders a disabled/inert checkbox. Verify a vitest test asserts the legend lists all catalog benchmarks with only S&P 500 checked by default.
- [x] 4.2 Extend `buildCombinedOption` to accept the selected, rebased benchmark lines and emit one ECharts line series each — dashed, thinner, and in muted palette colors distinct from the emerald portfolio line. Verify a vitest test asserts a benchmark line series is present and rebased to the combined curve's first point when an index is selected.
- [x] 4.3 Wire toggling a benchmark to add/remove its line from already-fetched data without a refetch, and re-rebase all drawn benchmark lines when the session selection changes. Verify vitest asserts toggling adds/removes a line (no new request) and that changing the selection re-rebases.
- [x] 4.4 Extend the chart tooltip to report each currently-drawn benchmark line's rebased USD value at the hovered date alongside the summed value and date, preserving German date formatting. Verify a vitest test asserts the tooltip includes a drawn benchmark's value.
- [x] 4.5 Ensure no benchmark lines are drawn in the empty state (no sessions selected). Verify a vitest test asserts the empty state shows no benchmark lines.

## 5. Frontend — verification gate

- [x] 5.1 Run `cd frontend && npm run -s typecheck && npx vitest run && npm run build` and verify all green.
