## Why

Both paper-trading charts plot lines with no axes, so a user can see the shape of
each curve but not read what any point means: there are no dates along the bottom
and no value/percentage scale up the side. On the single-session value chart the
portfolio-value line and the benchmark line are also unlabelled, so it is not clear
which line is which. This makes the charts hard to interpret and undercuts the point
of the comparison and benchmark views (telling which session/strategy performs best).

## What Changes

- The **paper-trading session comparison chart** (list page) gains a labelled x-axis
  (calendar dates) and a labelled y-axis whose ticks follow the active metric —
  percentages in the Return % view, USD amounts in the Value $ view. The existing
  color→session legend is kept.
- The **single-session value/benchmark chart** (session detail page) gains a labelled
  x-axis (dates) and a labelled y-axis (USD), plus a **legend** identifying which line
  is the portfolio value and which is the benchmark.
- Both charts stay dependency-free inline SVG (no chart library). Axis tick labels are
  rendered so they are not distorted by the charts' non-uniform SVG scaling, reusing
  the shared `formatCurrency` / `formatPercent` formatters.
- Purely presentational frontend work: no backend, API, schema, or migration change.

## Capabilities

### Modified Capabilities

- `app-shell`: "Paper-trading session comparison chart" gains labelled x/y axes;
  "Session value history chart" gains labelled x/y axes and a portfolio-vs-benchmark
  legend.

## Impact

- Frontend only: `frontend/src/pages/paper-trading/SessionComparisonChart.tsx` and
  `frontend/src/pages/paper-trading/SessionValueChart.tsx` (plus their co-located
  Vitest tests). No change to the pages that host them beyond what those components
  render.
- No backend/API/schema/migration change; no new dependencies.
