## Context

See proposal.md - Why. This is a frontend-only change to three existing
dependency-free inline-SVG line charts:

- `CombinedEquityChart.tsx` (dashboard) — single summed line; x mapped by
  **calendar time** (`Date.parse(date)`); point shape `{ date, value }`.
- `SessionComparisonChart.tsx` (paper-trading overview) — **multi-series** overlay
  with a Return %/Value $ metric toggle; x mapped by **calendar time**; each
  series has `points: { t, value }[]`.
- `SessionValueChart.tsx` (session detail) — single value line plus an optional
  dashed benchmark overlay; x mapped by **index** (`x(i)=pad+(i/(n-1))*(width-2*pad)`);
  point shape `SessionValueSnapshot { snapshot_date, total_value, benchmark_value|null }`.

All three share the same SVG geometry: `viewBox="0 0 800 160"`, `pad=8`,
`preserveAspectRatio="none"`, `vectorEffect="non-scaling-stroke"`,
`className="h-40 w-full"`, and all wrap their SVG in the shared `ChartAxes`
component. `ChartAxes` already renders axis tick labels as **HTML** (not SVG
`<text>`) precisely because `preserveAspectRatio="none"` stretches the x-axis and
would distort SVG text. None of the charts currently handle pointer events.

## Goals / Non-Goals

**Goals:**

- One shared, dependency-free hover mechanism reused by all three charts despite
  their two different x-projections (index vs calendar-time).
- A tooltip that reads correctly regardless of the SVG's non-uniform scaling.
- Keep existing axis labels, legends, metric toggle, benchmark overlay,
  placeholders, and loading/error states untouched; hover is purely additive.

**Non-Goals:**

- No backend/API/schema/migration change; no new npm dependency.
- The asset-detail `PriceSparkline` is out of scope.
- Rich interactions beyond "show value + date at the nearest point" (no zoom,
  pan, pinned tooltips, or range selection).

## Decisions

### D1 — HTML overlay tooltip, not SVG text

Render the tooltip as an absolutely-positioned HTML element inside a
`position: relative` wrapper around the chart, mirroring how `ChartAxes` already
escapes the `preserveAspectRatio="none"` distortion. An SVG `<text>` tooltip would
be stretched horizontally by the same non-uniform scaling that forced `ChartAxes`
to go HTML. An optional hover marker (dot/crosshair) is drawn **in** the SVG
because geometric marks scale predictably and `vectorEffect="non-scaling-stroke"`
keeps stroke widths crisp.

_Alternative considered:_ a charting library (recharts/visx) with built-in
tooltips — rejected: the project deliberately keeps charts dependency-free, and
adding one for a tooltip is disproportionate.

### D2 — Hit-test in rendered pixel space, not viewBox units

Pointer coordinates come back in CSS pixels relative to the container. Because the
SVG's 0–800 x-units are stretched to the container's rendered width, map the
pointer's `clientX` to a fraction of the container's **rendered** width
(`(clientX - rect.left) / rect.width`), exactly as `ChartAxes` positions its HTML
labels. Convert that fraction to the data domain to find the nearest point. Do not
use raw 0–800 viewBox units for hit-testing.

### D3 — A shared hook + two nearest-point strategies

Introduce a small shared helper (e.g. `useChartHover`) living alongside the
paper-trading charts, plus a shared HTML `ChartTooltip` presentation component.
The hook owns: pointer-move/enter/leave handling on the plot wrapper, computing
the cursor fraction (D2), delegating to a caller-supplied "nearest point" function,
and exposing the active hover state (data payload + pixel position) for the tooltip
and optional marker. Because nearest-point differs by x-projection, each chart
passes its own resolver:

- **Index-mapped** (`SessionValueChart`): `i = round(fraction * (n-1))`, clamped to
  `[0, n-1]`.
- **Calendar-time-mapped** (`CombinedEquityChart`, `SessionComparisonChart`):
  convert fraction to a time `t = minT + fraction*(maxT-minT)`, then pick the point
  with the smallest `|point.t - t|`. For the multi-series comparison chart, find the
  nearest point **across all plotted series** (compare on both time distance and,
  as a tiebreak, which series' point is closest) and surface that series' label +
  metric-aware value.

Keeping the geometry math in the hook (and resolvers per chart) avoids duplicating
the index-vs-time projection logic that already differs between these components.

### D4 — Metric-aware and benchmark-aware tooltip content

The tooltip payload is assembled by each chart so formatting stays local to where
the data semantics live:

- `CombinedEquityChart`: `{ date, value }` → `formatCurrency(value)`.
- `SessionComparisonChart`: `{ seriesLabel, date, value, metric }` → `formatPercent`
  in Return view, `formatCurrency` in Value view (reuse the existing `metric` state).
- `SessionValueChart`: `{ date, total_value, benchmark_value|null }` →
  `formatCurrency(total_value)` and, when `benchmark_value != null`,
  `formatCurrency(benchmark_value)`.

Dates: `formatAxisDate` yields short "M/D" for axis ticks; the tooltip wants a
fuller, timezone-safe date. Add a `formatTooltipDate(iso)` to `lib/format.ts` that
parses the `YYYY-MM-DD` parts directly (same approach as `formatAxisDate`) to avoid
the UTC day-shift, returning e.g. a medium date. For the comparison/equity charts
whose points carry an epoch `t`, format from the originating ISO date string, not a
`new Date(t)` that could reintroduce a tz shift — carry the source date onto the
plotted point if needed.

### D5 — Accessibility / input breadth

Mouse hover is the primary ask. The handlers are attached as pointer events so a
touch tap also surfaces the tooltip; `onPointerLeave` dismisses it. No keyboard
focus-walking of points in this change (kept minimal), but the plot wrapper will
not trap focus or break existing keyboard navigation.

## Risks / Trade-offs

- **[Rendered-width hit-testing depends on `getBoundingClientRect`]** → read the
  rect from the pointer event's `currentTarget` on each move so it reflects the
  current layout (responsive width), rather than caching a stale width.
- **[Nearest-across-series on the comparison chart can feel ambiguous when lines
  cross]** → resolve by nearest **point** (time then series distance); acceptable
  for a lightweight tooltip and matches "the point under the cursor".
- **[Tooltip clipping at chart edges]** → clamp the tooltip's horizontal offset
  within the container and flip its anchor near the right edge so it is not cut off.
- **[Test simulation of pointer geometry]** → jsdom has no real layout, so
  `getBoundingClientRect` returns zeros. Tests will stub the rect (or the resolver
  input) so a simulated `pointermove` deterministically selects a known point and
  asserts the tooltip's value+date text; this tests the wiring and formatting, not
  pixel-perfect geometry.

## Open Questions

None.
