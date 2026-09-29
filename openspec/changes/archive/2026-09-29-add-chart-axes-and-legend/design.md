## Context

See proposal.md — Why. Both charts are dependency-free inline SVG. `SessionValueChart`
and `SessionComparisonChart` render their lines in an SVG with
`viewBox="0 0 800 160"` and `preserveAspectRatio="none"`, which stretches the plot
horizontally to fill its container. Strokes stay crisp via `vectorEffect="non-scaling-stroke"`,
but any SVG `<text>` inside that SVG would be stretched horizontally along with the
plot and look wrong at typical panel widths. Both charts already compute the numeric
domain they plot against (min/max value + point count / date domain).

## Goals / Non-Goals

**Goals:**
- Labelled x-axis (dates) and y-axis (USD, or %/USD per the comparison chart's active
  metric) around both charts, rendered legibly at any panel width.
- A legend on the single-session value chart naming the portfolio-value line and the
  benchmark line.
- Stay dependency-free (no chart/D3 library); reuse `lib/format.ts` formatters.

**Non-Goals:**
- No backend/API/schema/migration change.
- No gridlines, hover tooltips, zoom, or configurable tick counts — a small fixed set
  of ticks is enough to read the chart.
- The comparison chart's existing color→session legend is unchanged (not re-designed).

## Decisions

- **Render axis tick labels as HTML around the SVG, not as SVG `<text>`.** Because the
  plot SVG uses `preserveAspectRatio="none"`, `<text>` would be distorted. Instead wrap
  the existing SVG in a small CSS layout: a y-axis label column to the left of the SVG
  and an x-axis label row beneath it. The SVG keeps rendering only polylines, so the
  non-scaling-stroke behavior and existing plot math are untouched. This avoids a chart
  library and keeps the change purely additive around the current SVG.
- **Fixed, domain-derived ticks.** Y-axis shows three labels (max, midpoint, min)
  derived from the same min/max the plot already computes, top-aligned to the plot box.
  X-axis shows the first and last date of the plotted domain (comparison chart: the
  shared calendar min/max; value chart: first and last snapshot date). Small and
  deterministic — easy to assert in tests.
- **Metric-aware y labels on the comparison chart.** Y tick labels format with
  `formatPercent` in the Return % view and `formatCurrency` in the Value $ view, and
  re-render when the toggle switches (they read the same `metric` state that already
  drives the plot).
- **Value-chart legend.** Two entries mirroring the comparison chart's legend style:
  "Portfolio value" keyed to the trend stroke color, and "Benchmark" keyed to the amber
  dashed style — the benchmark entry is shown only when the benchmark line is actually
  drawn (there are ≥2 non-null benchmark points), consistent with the existing overlay
  rule.
- **UTC-safe short date helper.** Add `formatAxisDate(iso)` to `lib/format.ts` that
  formats a `YYYY-MM-DD` snapshot date as a short `M/D` (or locale short) label without
  a timezone off-by-one (parse the date parts / format in UTC rather than
  `new Date(iso).toLocaleDateString()` in local time). Shared + unit-tested so both
  charts format dates identically.

## Risks / Trade-offs

- **Layout drift between HTML labels and the SVG plot.** Because labels live outside the
  SVG, they are aligned by CSS (label column height matches the plot height; first/last
  x labels sit under the plot's left/right edges) rather than by SVG coordinates. Minor
  sub-pixel misalignment is acceptable for read-at-a-glance axes; a small fixed padding
  keeps first/last x labels from clipping at the panel edges.
- **Only two/three ticks.** Intentionally coarse to stay legible on narrow panels; not a
  precise grid. Acceptable given the Non-Goals.
