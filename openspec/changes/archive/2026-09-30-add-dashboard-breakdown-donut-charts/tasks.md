## 1. Shared palette

- [x] 1.1 Lift the categorical palette out of `SessionComparisonChart.tsx` into a shared helper (e.g. `frontend/src/lib/palette.ts` exporting the color array + a cyclic `categoricalColor(index)`), and update `SessionComparisonChart.tsx` to import it. Verify: existing comparison-chart vitest tests still pass with unchanged colors/order.

## 2. Donut breakdown chart component

- [x] 2.1 Create a dependency-free inline-SVG donut component (rework `frontend/src/components/dashboard/BreakdownTile.tsx` or add `DonutBreakdownChart.tsx`) taking `{ title, entries: {key, count}[], formatKey }`. Draw one slice per entry sized by `count / total` using the shared palette, a hollow center showing the total count, and keep the existing card styling. Use an undistorted (square, default `preserveAspectRatio`) SVG. Verify: renders slices for sample entries and the total in the center.
- [x] 2.2 Add a legend mapping each slice color to its `formatKey`-humanized label, largest-first (backend order). Verify: legend lists every entry with its color swatch.
- [x] 2.3 Add per-slice hover AND keyboard-focus interaction that reveals the entry's humanized label, exact count (`toLocaleString()`), and percentage (`formatPercent(count/total)` from `lib/format.ts`); make the same detail reachable from the legend rows. Slices/legend entries are focusable with an `aria-label` carrying the same detail. Verify: hovering/focusing a slice or legend row shows label + count + percentage.
- [x] 2.4 Preserve the "No data yet" empty state when `entries` is empty (no chart drawn). Verify: empty entries render the empty-state message, not a chart.

## 3. Dashboard wiring

- [x] 3.1 In `frontend/src/pages/dashboard/DashboardPage.tsx`, render the by-category and by-sector breakdowns with the donut component, still passing `data.assets.by_category` / `by_sector` and `humanize`. Verify: dashboard shows two donut charts.

## 4. Tests + verification

- [x] 4.1 Add/adjust vitest tests: donut renders a slice per entry with correct percentages, center total, legend, hover/focus reveals label+count+percentage, and the empty state. Update any existing `BreakdownTile` tests to the new presentation.
- [x] 4.2 Frontend: `npm run typecheck && npx vitest run && npm run build` all green.
- [x] 4.3 `openspec validate add-dashboard-breakdown-donut-charts --strict` passes.
