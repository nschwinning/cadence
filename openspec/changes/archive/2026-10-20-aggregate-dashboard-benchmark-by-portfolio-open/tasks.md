## 1. Backend — overview payload

- [x] 1.1 Add a `contributions` field to `DashboardSessionPerformance` in `backend/src/cadence/api/schemas.py` — a list of `{ effective_date: date, amount: float }` — with a docstring explaining it is the session's opening capital plus later capital increases, used by the client to build the benchmark comparison line.
- [x] 1.2 In `backend/src/cadence/dashboard/service.py::_session_performance`, populate `contributions` for each session using `paper_trading/service.py::session_contributions` (reuse the same events/start-date basis the session detail uses), so the opening contribution matches the session's actually deployed capital.
- [x] 1.3 Leave the benchmark price series (`_benchmark_overlays`) returning raw index closes windowed to the range (shape unchanged); update any docstring/comment that claims the client rebases to the combined start to instead describe the per-session aggregation.
- [x] 1.4 Confirm the empty-system and missing-price-history paths still return catalog entries with empty series and zeroed/empty contributions rather than erroring.

## 2. Backend — tests

- [x] 2.1 Test that `_session_performance` returns each session's contributions (opening capital at start date + a capital-increase event), with correct effective dates and amounts.
- [x] 2.2 Test the overview still lists every catalog benchmark with raw price series windowed to the range, and lists empty series for benchmarks without stored prices in the range (no omission, no error). (Covered by existing `test_benchmark_series_windowed_with_anchor_and_names` + `test_benchmark_without_prices_is_present_but_empty`, re-run green.)
- [x] 2.3 Test the empty-system overview returns empty session collections and benchmark catalog entries with empty series. (Covered by existing `test_overview_empty_system_is_zeroed` + `test_benchmark_series_empty_system_lists_catalog_with_empty_points`, plus new `test_session_without_snapshots_has_no_contributions`.)

## 3. Frontend — aggregation

- [x] 3.1 In `frontend/src/types/api.ts`, add `contributions: { effective_date: string; amount: number }[]` to `DashboardSessionPerformance` (mirror the backend schema).
- [x] 3.2 In `frontend/src/pages/dashboard/aggregate.ts`, replace `rebaseBenchmarkLine` with a pure aggregator that, given the selected sessions, an index's ascending closes, and the common date axis, returns the USD benchmark line = `close_on_or_before(t) × Σ(contribution.amount / close_on_or_before(contribution.effective_date))` over the selected sessions' contributions with `effective_date ≤ t`. Include a client `close_on_or_before` bisect helper mirroring the backend; a contribution predating all closes contributes zero units.
- [x] 3.3 Ensure the aggregated line is evaluated on the same date axis as `combinedSeries`, starts at zero before the first selected session opens, and steps up on each session open and capital increase.

## 4. Frontend — chart

- [x] 4.1 In `frontend/src/pages/dashboard/CombinedEquityChart.tsx`, build each selected benchmark line from the new aggregator over the selected sessions (not `rebaseBenchmarkLine`); keep the legend, `DEFAULT_BENCHMARK_ID = 'SP500'`, dashed styling, and the inert/disabled state for an index with no price data.
- [x] 4.2 Re-aggregate benchmark lines when the session selection or benchmark selection changes, without issuing a new request (reuse already-fetched data, same memo pattern as the equity line).
- [x] 4.3 Update the hover tooltip to report each drawn benchmark line's aggregated USD value at the nearest point. (Tooltip formatter already renders every drawn series' USD value via `formatCurrency`; benchmark lines now carry aggregated dollar values, so no formatter change was needed.)
- [x] 4.4 Preserve the empty state: when no session is selected, draw neither equity nor benchmark lines. (`SummedCurve` short-circuits on `hasSelection`; `benchmarkDollarSeries` returns `[]` for an empty date axis.)

## 5. Frontend — tests

- [x] 5.1 Unit-test the new aggregator: two sessions opened on different dates sum, the line steps up on the second session's open date, a capital-increase contribution adds a step-up, and an index with no stored closes (or contributions before all closes) yields zero/no line. Remove obsolete `rebaseBenchmarkLine` tests.
- [x] 5.2 Test `CombinedEquityChart` sums the benchmark across exactly the selected sessions — toggling a session off drops both the equity line and the benchmark line — using already-fetched data (no refetch).
- [x] 5.3 Test the default S&P 500 line renders in USD as the aggregated per-session buy-and-hold (not a single rebased curve), and that an empty-history index stays inert.
- [x] 5.4 Update existing dashboard tests (`aggregate.test.ts`, `CombinedEquityChart` test, any dashboard service test) for the contributions field and the new benchmark shape.

## 6. Verify

- [x] 6.1 Backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`. (ruff clean, mypy 99 files clean, 902 pytest passed.)
- [x] 6.2 Frontend gates: `cd frontend && npm run -s typecheck && npx vitest run && npm run build`. (typecheck clean, 265 vitest passed, build OK.)
- [x] 6.3 `openspec validate aggregate-dashboard-benchmark-by-portfolio-open --strict`. (valid.)
