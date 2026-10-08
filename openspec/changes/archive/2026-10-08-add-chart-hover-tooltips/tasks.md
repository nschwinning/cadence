## 1. Shared hover primitives

- [x] 1.1 Add `formatTooltipDate(iso)` to `frontend/src/lib/format.ts` that parses `YYYY-MM-DD` parts directly (like `formatAxisDate`, timezone-safe, no UTC day-shift) and returns a fuller medium date; verify with a co-located unit test asserting a known ISO date formats without day-shift.
- [x] 1.2 Add a shared `useChartHover` hook (alongside the paper-trading charts) that attaches pointer enter/move/leave handlers to the plot wrapper, computes the cursor fraction from the pointer `clientX` against the container's rendered width (`getBoundingClientRect` on the event target, per design D2), delegates to a caller-supplied nearest-point resolver, and exposes active hover state (payload + pixel position) plus a dismiss-on-leave; verify via a hook/unit test (or through the chart tests in groups 2–4) that a simulated `pointermove` with a stubbed rect selects the expected point and a `pointerleave` clears it.
- [x] 1.3 Add a shared `ChartTooltip` HTML-overlay presentation component (absolutely positioned within a `position: relative` chart wrapper, edge-clamped so it is not clipped) that renders the passed value/date lines; verify it renders its content and is not an SVG `<text>` element via a small render test.

## 2. Session value chart (detail page)

- [x] 2.1 Wire `useChartHover` into `SessionValueChart.tsx`/`ValueCurve` with an **index-mapped** resolver (`i = round(fraction*(n-1))` clamped to `[0,n-1]`), render `ChartTooltip` showing the snapshot date (`formatTooltipDate`) and portfolio value (`formatCurrency`), and the benchmark value (`formatCurrency`) when `benchmark_value != null`; optionally draw an SVG hover marker. Verify the detail chart still renders axes, legend, and both lines unchanged.
- [x] 2.2 Extend `SessionValueChart.test.tsx` to simulate a hover over the plot and assert the tooltip shows the nearest snapshot's value and date, that the benchmark value appears when present, and that leaving the plot dismisses the tooltip; verify the test passes.

## 3. Session comparison chart (overview page)

- [x] 3.1 Wire `useChartHover` into `SessionComparisonChart.tsx`/`ComparisonCurves` with a **calendar-time** resolver that finds the nearest plotted point across all series (time distance, series distance as tiebreak), render `ChartTooltip` showing the series label, date (`formatTooltipDate` from the point's source ISO date), and value formatted for the active metric (`formatPercent` in Return %, `formatCurrency` in Value $); optionally draw an SVG hover marker. Verify the chart still renders the legend, metric toggle, and axes unchanged.
- [x] 3.2 Extend `SessionComparisonChart.test.tsx` to simulate a hover and assert the tooltip shows the nearest series' label, value, and date; assert the tooltip value formatting tracks the metric toggle (percentage in Return view, USD in Value view); assert dismiss-on-leave; verify the test passes.

## 4. Dashboard combined equity curve

- [x] 4.1 Wire `useChartHover` into `CombinedEquityChart.tsx`/`SummedCurve` with a **calendar-time** resolver (nearest point by time), render `ChartTooltip` showing the date (`formatTooltipDate`) and summed equity value (`formatCurrency`); carry the source ISO date onto the plotted point if needed for tz-safe formatting; optionally draw an SVG hover marker. Verify hover is suppressed when the no-selection empty state is shown.
- [x] 4.2 Extend `CombinedEquityChart.test.tsx` to simulate a hover over the equity line and assert the tooltip shows the summed value and date at the nearest point, and that leaving dismisses it; verify the test passes.

## 5. Verification gate

- [x] 5.1 Run `cd frontend && npm run typecheck && npx vitest run && npm run build` and verify typecheck, all Vitest suites, and the production build pass.
