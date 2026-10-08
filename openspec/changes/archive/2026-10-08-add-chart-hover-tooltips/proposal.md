## Why

The three timeseries line charts — the dashboard combined equity curve, the
paper-trading session-comparison chart, and the single-session value chart — plot
their lines but give no way to read an individual data point. A user can see the
shape of a curve but cannot tell what value a point had or on what date. Adding a
hover tooltip that reveals the exact value and date at the point under the cursor
makes the charts readable rather than merely decorative.

## What Changes

- Add a **hover tooltip** to the three line charts. Moving the pointer over a
  chart highlights the nearest plotted data point and shows a small tooltip with
  that point's **value and date**.
  - **Dashboard combined equity curve** (`CombinedEquityChart`): tooltip shows the
    summed equity value (USD) and the date at the hovered point.
  - **Paper-trading session-comparison chart** (`SessionComparisonChart`): the
    tooltip identifies the **nearest point across the plotted series** and shows
    that session's label, its value, and the date. The value is **metric-aware** —
    a percentage in the Return % view and a USD amount in the Value $ view.
  - **Session value chart** (`SessionValueChart`): tooltip shows the portfolio
    value (USD) and the date; when a benchmark value exists at that point, the
    tooltip also shows the benchmark value.
- The tooltip is rendered as an **HTML overlay** (not SVG text) so it is not
  distorted by the charts' `preserveAspectRatio="none"` x-stretching — the same
  reason the existing `ChartAxes` renders tick labels as HTML. Hit-testing maps
  the pointer against the container's rendered pixel width. An optional hover
  marker/crosshair may be drawn in the SVG using the existing non-scaling-stroke
  pattern.
- Existing axis labels, legends, metric toggle, benchmark overlay, placeholders,
  and loading/error states are **unchanged**; the tooltip is additive.

## Capabilities

### New Capabilities

<!-- None. -->

### Modified Capabilities

- `app-shell`: The three existing chart requirements gain hover-tooltip behavior:
  - **Session value history chart** — hovering reveals the portfolio value (and
    benchmark value when present) and date at the nearest point.
  - **Paper-trading session comparison chart** — hovering reveals the nearest
    series' label, metric-aware value, and date.
  - **Dashboard combined equity curve** — hovering reveals the summed value and
    date at the nearest point.

## Impact

- **Frontend only.** No backend, API, schema, or migration changes; no new
  dependency (charts stay dependency-free inline SVG).
- Affected components: `frontend/src/pages/dashboard/CombinedEquityChart.tsx`,
  `frontend/src/pages/paper-trading/SessionComparisonChart.tsx`,
  `frontend/src/pages/paper-trading/SessionValueChart.tsx`.
- A small shared hover helper/hook and a shared HTML tooltip presentation are
  introduced so both the index-mapped and calendar-time-mapped charts reuse the
  same nearest-point and rendering logic. A tooltip date formatter is added to
  `frontend/src/lib/format.ts` (timezone-safe, like the existing `formatAxisDate`).
- Co-located Vitest tests are extended for each of the three chart components.
- Out of scope: the asset-detail `PriceSparkline` (not one of the three requested
  surfaces), and any change to axis labels or legends.
