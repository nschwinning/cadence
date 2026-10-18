## Why

The paper-trading page's two charts (the single-session value chart and the multi-session comparison chart) are hand-rolled inline SVGs, and three things make them hard to read and trust:

1. **Sessions are unstably ordered.** The session list and the comparison chart follow the backend's `updated_at DESC` listing, so the row order and the chart's line order shuffle whenever any session is touched.
2. **A portfolio's line changes color between renders.** Colors are assigned by render index over that unstable order, so the same portfolio is drawn in different colors from one visit to the next — you cannot learn "my green line."
3. **The x-axis shows only two date labels** (first and last), so it is hard to place any point in time.

Moving to a real charting library (Apache ECharts) removes the bespoke SVG/axis/hover machinery, gives us proper multi-tick dated axes for free, and lets us fix ordering and color stability cleanly.

## What Changes

- **Migrate both paper-trading charts to Apache ECharts.** Replace the hand-rolled SVG in `SessionValueChart.tsx` and `SessionComparisonChart.tsx` with ECharts (core + LineChart + Grid/Tooltip/Legend components, SVG renderer) via a small `useRef`/`useEffect` React wrapper (no `echarts-for-react`, to avoid its React 19 peer-dependency lag). All existing behavior is preserved: the %/$ metric toggle (default Return %), the benchmark overlay and legend, hover tooltips, the end-of-day indicator, the "not enough history" / insufficient-data placeholders, and the loading/error states.
- **Give sessions one stable order everywhere: creation date, oldest first.** The paper-trading session list and the comparison chart's lines and legend SHALL both order sessions by creation date, oldest first. New sessions therefore always append at the end.
- **Give each portfolio a stable color keyed to its identity.** A session's line color SHALL be derived from the session's own stable identity (not its position in the current render), so the same portfolio keeps the same color across visits and regardless of which other sessions are plotted or archived.
- **Show more dated x-axis ticks** (roughly 5–6 evenly spaced calendar-date labels) on both charts instead of just the first and last.

Out of scope (noted as a follow-up): the dashboard's `CombinedEquityChart.tsx` is **not** migrated in this change.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `app-shell`: The **Portfolio and paper-trading views** requirement gains a stable session-ordering guarantee (creation date, oldest first). The **Session value history chart** and **Paper-trading session comparison chart** requirements are updated so both charts render with multiple dated x-axis labels, and the comparison chart orders its lines/legend oldest-first with each session's color keyed to its stable identity. (These modify behavior introduced by the archived `add-session-comparison-chart` and `add-chart-axes-and-legend` changes.)
- `ai-paper-trading`: The **Multi-session comparison value history read** requirement gains an ordering guarantee — the response lists sessions by creation date, oldest first — so the chart's stable order has a stable source.

## Impact

- **Frontend:** `frontend/src/pages/paper-trading/SessionValueChart.tsx`, `SessionComparisonChart.tsx`, and the list-ordering in `PaperTradingPage.tsx`; shared helpers `ChartAxes.tsx`, `lib/palette.ts`, and `lib/format.ts` are affected (axis-tick generalization, stable color keying). New dependency: `echarts`. Affected tests: `SessionValueChart.test.tsx`, `SessionComparisonChart.test.tsx`, `PaperTradingPage.test.tsx`, `format.test.ts`.
- **Backend:** `list_sessions_value_comparison` in `paper_trading/service.py` orders its returned series oldest-first. No new API shape, no schema change, no migration.
- **Not touched:** the dashboard `CombinedEquityChart.tsx`; the value-comparison and session-read API payload shapes; database schema.
