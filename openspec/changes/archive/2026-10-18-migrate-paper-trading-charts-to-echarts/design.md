## Context

See `proposal.md` — Why. The two paper-trading charts (`SessionValueChart.tsx`, `SessionComparisonChart.tsx`) are hand-rolled inline SVGs that share bespoke helpers: `ChartAxes.tsx` (HTML axis labels overlaid on a `preserveAspectRatio="none"` SVG, with `xLabels` typed as a 2-tuple), `useChartHover.ts` + `ChartTooltip.tsx` (pointer→nearest-point hover), and `lib/palette.ts` (`categoricalColor(index)`). No charting library is currently installed. Comparison colors are assigned by render index (`colorFor(index)`), and render order follows the backend's `updated_at DESC` listing, so colors and positions are unstable. The x-axis shows only the first and last dates.

Constraints that shape the approach:
- **React 19.** `echarts-for-react` lags React 19 peer deps, so we integrate `echarts` core directly.
- **jsdom tests.** Vitest runs in jsdom, which has no layout/canvas. The current tests assert on DOM (axis-label spans, `polyline`/`comparison-line` elements, tooltip text). ECharts' SVG renderer produces real DOM nodes that jsdom can hold, but it still needs a non-zero container size, which jsdom does not provide.
- **Existing spec behavior must be preserved** across the migration: %/$ toggle (default Return %), benchmark overlay + legend, hover tooltips, end-of-day badge, baseline, insufficient-data / not-enough-history placeholders, loading/error states, archived exclusion.

## Goals / Non-Goals

**Goals:**
- Render both paper-trading charts with Apache ECharts via a thin, reusable React wrapper.
- One stable session order (creation date, oldest first) shared by the list and the comparison chart.
- Each session's comparison-chart color keyed to the session's stable identity, not its render index.
- Several dated x-axis ticks on both charts.
- Keep all externally observable behavior from the current specs (the migrated charts remain testable in jsdom).

**Non-Goals:**
- Migrating the dashboard `CombinedEquityChart.tsx` (separate follow-up).
- Changing the comparison/session-read API payload shapes, the DB schema, or adding a migration.
- Changing the backend `list_sessions` global ordering (only the comparison read is ordered).
- Introducing `echarts-for-react` or the canvas renderer.

## Decisions

### D1: `echarts` core + a small `useRef`/`useEffect` wrapper, SVG renderer, tree-shaken imports
Import from `echarts/core` and register only what we use: `LineChart`, and the `GridComponent`, `TooltipComponent`, `LegendComponent`, `MarkLineComponent` (for the Return % baseline), plus `SVGRenderer`. A `EChart` wrapper component owns a `div` ref, calls `echarts.init(el, undefined, { renderer: 'svg' })` once, calls `setOption(option, { notMerge: true })` whenever the `option` prop changes, wires a `ResizeObserver` (or window resize) to `chart.resize()`, and disposes on unmount.
- *Why:* avoids the `echarts-for-react` React-19 peer-dep problem; SVG renderer yields inspectable DOM (good for jsdom and for crisp axis text, replacing the `ChartAxes` HTML-overlay workaround); tree-shaking keeps the bundle small.
- *Alternatives:* `echarts-for-react` (peer-dep lag, less control); Recharts (user explicitly chose ECharts); keep hand-rolled SVG (does not solve multi-tick axes cleanly and keeps the bespoke hover/axis code).

### D2: Stable order = creation date, oldest first, applied in two places
- **Backend:** `list_sessions_value_comparison` sorts its series by session `created_at` ascending (data already loaded via `list_sessions`; no new query, no schema change). This gives the comparison chart a stable source order. (ai-paper-trading spec.)
- **Frontend:** `PaperTradingPage.tsx` sorts the session list by `created_at` ascending before rendering (the session read already exposes `created_at`). (app-shell spec.)
- *Why oldest-first:* new sessions append at the end, so existing rows/lines never shift — the property the user asked for.
- *Alternative:* change `list_sessions` global order — rejected; it is used broadly (dashboards, archive-aware listing) and would have wider, unintended effects.

### D3: Comparison color keyed to session identity, not render index
Replace `colorFor(index)` with a deterministic map from the session's id (a stable UUID) to a palette slot: hash the id string to an integer and index `CATEGORICAL_PALETTE`. Add a `colorForKey(key: string)` helper to `lib/palette.ts` alongside the existing `categoricalColor(index)` (which the dashboard donuts still use).
- *Why:* the same session always gets the same color regardless of order, membership, or archiving — satisfies "always the same color." Combined with D2 it is also collision-light in practice.
- *Trade-off:* two different sessions can hash to the same palette slot (only 8 colors). Acceptable and far better than today's shuffling; the legend always disambiguates by label. (See Risks.)
- *Alternative:* color by oldest-first rank index — rejected because archiving/unarchiving a middle session shifts later sessions' indices and thus their colors.

### D4: Multi-tick dated x-axis
Let ECharts' time/category axis place roughly 5–6 evenly spaced ticks, formatted with the existing timezone-safe `formatAxisDate` (M/D) via the axis `formatter`. This removes the `ChartAxes` 2-tuple `xLabels` constraint.
- *Why:* native axis tick management replaces the bespoke first/last-only labels; `formatAxisDate` keeps formatting UTC-safe and consistent.

### D5: jsdom testability
ECharts needs a sized container. In the test setup, stub the chart container's measured size (e.g., mock `getBoundingClientRect`/`clientWidth`/`clientHeight` on the wrapper, or pass an explicit width/height to `echarts.init`) so the SVG renderer draws. Tests then assert on rendered SVG/DOM and on the pure data-prep functions (series building, color keying, axis label set). Where DOM assertions are brittle under jsdom + ECharts, pull the chart's logic into pure helpers (series/option builders) and unit-test those directly, keeping a lighter smoke test that the chart mounts and shows the expected placeholder/loading/error states.
- *Why:* preserves meaningful coverage of the spec behaviors without depending on real layout/paint.

### D6: Fate of the bespoke helpers
`ChartAxes.tsx`, `useChartHover.ts`, and `ChartTooltip.tsx` are used **only** by these two charts (confirmed before edit). Once both charts move to ECharts (which provides axes, tooltip, and hover natively) these become dead code and are removed. `lib/format.ts` (`formatAxisDate`, `formatTooltipDate`, `formatCurrency`, `formatPercent`) stays — reused as ECharts axis/tooltip formatters. `lib/palette.ts` stays and gains `colorForKey`.
- *Guard:* before deleting any shared helper, re-grep for other importers; if one exists outside these two charts, keep it.

## Risks / Trade-offs

- **[Color collisions]** Two sessions may share a palette slot (8 colors). → Mitigation: the legend always shows the label; collisions are cosmetic and rare for the handful of concurrent sessions in practice. If it becomes a problem, a later change can widen the palette or use a perceptual-spacing assignment — no spec change needed.
- **[jsdom rendering gaps]** ECharts may render little/nothing without a sized container. → Mitigation: D5 (stub container size + test pure builders); keep DOM smoke tests minimal and resilient.
- **[Bundle size]** `echarts` is sizable. → Mitigation: import only core + the registered components/charts + SVG renderer (tree-shaking); `npm run build` verifies the result builds.
- **[Behavior regressions during rewrite]** The hand-rolled charts encode subtle behavior (baseline in Return % view, legend-only sessions, metric-remount clearing stale hover). → Mitigation: the app-shell spec enumerates each behavior as a scenario; port them one-for-one and keep/translate the corresponding tests.
- **[Lost test granularity]** Some current tests assert exact SVG internals (e.g. `['1/4','1/6']` axis tuples, `comparison-line` count). → Mitigation: rewrite those assertions against ECharts output or against the extracted pure builders; update the hardcoded 2-tick expectations to the new multi-tick behavior.

## Migration Plan

Frontend-plus-one-backend change; no DB migration, no data backfill, no deployment ordering constraint.
1. Add `echarts` to `frontend/package.json`.
2. Backend: order `list_sessions_value_comparison` oldest-first; add/adjust its test.
3. Frontend: add the `EChart` wrapper + `colorForKey`; migrate `SessionValueChart.tsx` and `SessionComparisonChart.tsx`; sort the list in `PaperTradingPage.tsx`; remove now-dead `ChartAxes`/`useChartHover`/`ChartTooltip` (after the import re-grep); update tests.
4. Verify gates: backend `uv run ruff check . && uv run mypy src/cadence && uv run pytest`; frontend `npm run typecheck && npm run test && npm run build`.

Rollback: revert the commit; no persisted state changes, so nothing to undo in the database.
