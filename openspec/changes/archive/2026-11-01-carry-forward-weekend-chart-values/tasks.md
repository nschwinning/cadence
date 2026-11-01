## 1. Shared carry-forward helper

- [x] 1.1 Add a pure carry-forward/date-axis helper (e.g. `frontend/src/lib/carryForward.ts` or a charts util): given one or more series of `{date, value}` points plus a horizon date, build the sorted de-duplicated union date axis extended to `max(latest date, horizon)`, and map each series onto it with last-observation-carried-forward (value = most recent point on/before each date; no value before the series' first point). Include a `todayEt()`/horizon helper returning the current `America/New_York` date as `YYYY-MM-DD`, reusing `lib/format.ts` date handling. Verify with new vitest unit tests covering: LOCF over a union axis, interior gap fill, trailing extension to the horizon, no backfill before first point, empty/single-point/empty-axis edge cases, and determinism.

## 2. Session comparison chart

- [x] 2.1 Wire the helper into `pages/paper-trading/SessionComparisonChart.tsx` so each plotted session is carried forward over the union of all displayed sessions' dates extended to today (ET), with the metric (Return % / Value $) computed from the carried-forward value. Verify the existing `SessionComparisonChart` vitest suite still passes.
- [x] 2.2 Add a vitest case (mocked EChart inspecting `data-option`) asserting that an equity-only session whose latest point is Friday is drawn flat across the weekend at its Friday value alongside a session with weekend points, instead of ending at Friday. Verify the new test passes.

## 3. Single-session value chart

- [x] 3.1 Wire the helper into `pages/paper-trading/SessionValueChart.tsx` to carry the value line and its benchmark overlay forward to today (ET). Verify the existing `SessionValueChart` vitest suite still passes.
- [x] 3.2 Add a vitest case asserting the value (and benchmark) line extends flat from the last snapshot to the current day over a trailing non-trading day. Verify the new test passes.

## 4. Dashboard combined equity curve

- [x] 4.1 Extend the shared date axis fed to `pages/dashboard/aggregate.ts` (`combinedSeries` / `benchmarkDollarSeries`) so it includes the today (ET) horizon, keeping their existing LOCF behavior intact, and wire it through `components/dashboard/CombinedEquityChart.tsx`. Verify the existing `aggregate.test.ts` and `CombinedEquityChart.test.tsx` suites still pass.
- [x] 4.2 Add vitest cases asserting the combined line and each drawn benchmark line extend flat to the current day when the latest selected-session snapshot is a prior trading day. Verify the new tests pass.

## 5. Verification

- [x] 5.1 Run `cd frontend && npm run typecheck && npm run test && npm run build` and confirm all pass.
- [x] 5.2 Confirm no backend file changed (the snapshot job, endpoints, KPIs, and P&L/learning jobs are untouched); run `openspec validate --strict` and confirm the change is valid.
