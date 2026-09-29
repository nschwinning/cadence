## 1. Shared date formatter

- [x] 1.1 Add a UTC-safe `formatAxisDate(iso)` helper to `frontend/src/lib/format.ts` that turns a `YYYY-MM-DD` date into a short `M/D`-style label without a local-timezone off-by-one; verify a unit test in `format.test.ts` (e.g. `2026-01-04` → `1/4`, and a date that would shift a day under local-time parsing stays correct)

## 2. Session value / benchmark chart

- [x] 2.1 In `frontend/src/pages/paper-trading/SessionValueChart.tsx`, wrap the existing plot SVG in a layout that adds an HTML y-axis label column (USD ticks: max/mid/min from the chart's computed min/max via `formatCurrency`) and an HTML x-axis label row (first and last snapshot date via `formatAxisDate`), leaving the SVG polylines untouched; add a legend with a "Portfolio value" entry (trend stroke color) and a "Benchmark" entry (amber dashed) shown only when the benchmark line is drawn; keep the existing <2-snapshot placeholder / loading / error behavior. Verify co-located Vitest tests: axis labels render (a USD y-label and a dated x-label), the legend names both lines when benchmark values are present and only the portfolio line when they are absent, and no axes/legend-benchmark entry appear in the placeholder state

## 3. Session comparison chart

- [x] 3.1 In `frontend/src/pages/paper-trading/SessionComparisonChart.tsx`, wrap the plot SVG in the same axis layout: an HTML y-axis label column whose ticks are formatted with `formatPercent` in the Return % view and `formatCurrency` in the Value $ view (max/mid/min from the per-metric domain) and re-render when the toggle switches, plus an HTML x-axis label row with the first and last calendar date (via `formatAxisDate`) of the shared time domain; keep the existing color→session legend, the insufficient-data placeholder (no axes when nothing is plotted), and loading/error states. Verify co-located Vitest tests: axis labels render when at least one line is plotted, the y-axis labels are percentages by default and become USD after toggling to Value $, and the placeholder state shows no axis labels

## 4. Verification

- [x] 4.1 Run `npm run typecheck && npx vitest run && npm run build` in `frontend/` and confirm all green
- [x] 4.2 Run `openspec validate add-chart-axes-and-legend --strict` and confirm it passes
