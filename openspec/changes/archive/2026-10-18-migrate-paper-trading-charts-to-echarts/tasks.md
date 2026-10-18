## 1. Backend: stable comparison order

- [x] 1.1 In `backend/src/cadence/paper_trading/service.py`, order the series returned by `list_sessions_value_comparison` by session `created_at` ascending (oldest first), reusing the already-loaded `list_sessions` rows (no new query, no schema change). Verify by inspection that no new DB round-trip is introduced.
- [x] 1.2 Add/extend a service test asserting the comparison read returns sessions ordered oldest-created first (and that archived sessions remain excluded and snapshot-less sessions still appear with empty points). Verify `cd backend && uv run pytest` passes for the paper-trading service tests.
- [x] 1.3 Verify backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` all pass. (ruff + mypy clean, 859 pytest green.)

## 2. Frontend: ECharts dependency and wrapper

- [x] 2.1 Add `echarts` to `frontend/package.json` and verify `npm install` succeeds and `npm run build` still builds.
- [x] 2.2 Create a reusable `EChart` React wrapper (ref + `echarts.init` with `{ renderer: 'svg' }`, `setOption(option, { notMerge: true })` on prop change, resize handling, dispose on unmount) importing only `echarts/core` + `LineChart` + `GridComponent`/`TooltipComponent`/`LegendComponent`/`MarkLineComponent` + `SVGRenderer`. Verify a smoke test mounts the wrapper with a sized container and renders an SVG node.
- [x] 2.3 Add `colorForKey(key: string)` to `frontend/src/lib/palette.ts` (deterministic hash of the key → `CATEGORICAL_PALETTE` slot), keeping the existing `categoricalColor(index)`. Verify a unit test shows the same key always maps to the same color and different keys spread across the palette.
- [x] 2.4 Add a jsdom test helper/setup that gives the chart container a non-zero measured size so the SVG renderer draws, and verify an `EChart` instance produces SVG output under Vitest.

## 3. Frontend: migrate the single-session value chart

- [x] 3.1 Rewrite `frontend/src/pages/paper-trading/SessionValueChart.tsx` to render via `EChart`: portfolio-value line plus the benchmark overlay line, legend naming both lines (benchmark absent when not drawn), several dated x-axis ticks via `formatAxisDate`, USD y-axis via `formatCurrency`, native hover tooltip reporting date + portfolio value (+ benchmark value when present) via `formatTooltipDate`/`formatCurrency`, the end-of-day badge/hint, the "not enough history" placeholder (<2 snapshots), and loading/error states. Verify against the app-shell "Session value history chart" scenarios.
- [x] 3.2 Update `SessionValueChart.test.tsx` to the ECharts output / extracted pure builders — including replacing the hardcoded 2-tick x-axis expectation with the multi-tick behavior, and keeping coverage of benchmark-present/absent, placeholder, and loading/error. Verify `npm run test` passes for this file.

## 4. Frontend: migrate the comparison chart

- [x] 4.1 Rewrite `frontend/src/pages/paper-trading/SessionComparisonChart.tsx` to render via `EChart`: one line per session with ≥2 points on a shared y-scale; %/$ metric toggle defaulting to Return %; Return-% baseline at 0 (via mark-line) in the return view only; several dated x-axis ticks; y-axis + tooltip formatted for the active metric; legend mapping each session to its color (including legend-only sessions with <2 points); insufficient-data placeholder and loading/error states. Verify against the app-shell comparison-chart scenarios.
- [x] 4.2 Order the comparison chart's lines and legend by session creation date oldest-first (relying on the backend order from task 1.1) and key each session's color to its stable identity via `colorForKey(session_id)` instead of render index. Verify a session keeps the same color across renders and when the plotted set changes.
- [x] 4.3 Update `SessionComparisonChart.test.tsx` to the ECharts output / extracted pure builders — replace the hardcoded 2-tick x-axis expectation, assert identity-keyed stable colors and oldest-first order, and keep coverage of the metric toggle, legend-only sessions, placeholder, and loading/error. Verify `npm run test` passes for this file.

## 5. Frontend: stable session-list order

- [x] 5.1 In `frontend/src/pages/paper-trading/PaperTradingPage.tsx`, sort the rendered session list by `created_at` ascending (oldest first) regardless of backend/update order. Verify against the app-shell "Stable paper-trading session ordering" scenarios.
- [x] 5.2 Update `PaperTradingPage.test.tsx` to assert the oldest-first list order (and that a newly created session appends at the end). Verify `npm run test` passes for this file.

## 6. Cleanup and final verification

- [x] 6.1 Re-grep the codebase for importers of `ChartAxes.tsx`, `useChartHover.ts`, and `ChartTooltip.tsx`; if nothing outside the two migrated charts uses them, delete them (and their tests), plus update `format.test.ts` only if its covered helpers' usage changed. Verify no dangling imports remain (`npm run typecheck`). (Re-grep shows the out-of-scope dashboard `CombinedEquityChart.tsx` still imports all three helpers + `categoricalColor`, so they are KEPT — no deletion. Typecheck clean.)
- [x] 6.2 Verify frontend gates: `cd frontend && npm run typecheck && npm run test && npm run build` all pass.
- [x] 6.3 Verify the dashboard `CombinedEquityChart.tsx` is unchanged and still passes its tests (confirm it was left out of scope).
