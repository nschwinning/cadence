## Context

The dashboard renders two breakdowns — `by_category` and `by_sector` — as ranked `{key, count}` lists inside `BreakdownTile.tsx`. This change turns each into an interactive donut chart. It is the codebase's first pie/donut chart and its first chart hover-tooltip, so the notable decisions are how to draw slices in dependency-free SVG and how to expose per-slice detail.

## Goals / Non-Goals

**Goals**
- Donut chart per breakdown, slice size ∝ share of total, total count in the center, color→label legend.
- Hover/focus a slice → label + exact count + percentage.
- Frontend only; consume the existing `{key, count}` arrays; keep humanized labels and the empty state.

**Non-Goals**
- No backend/schema/API change; no new percentage field from the server.
- No new charting dependency.
- Not touching the dashboard's `StatTile` summary tiles or `HealthIndicator`.

## Decisions

### Rendering: SVG arc donut, no library
Draw each slice as an SVG `<path>` arc between cumulative start/end angles computed from the running sum of counts. Use a viewBox-based square SVG with `preserveAspectRatio` left at the default (`xMidYMid meet`) so arcs are **not** distorted — unlike the line charts (`SessionComparisonChart.tsx`) which use `preserveAspectRatio="none"`; a donut must keep a 1:1 aspect ratio or circles become ellipses. The hollow center is achieved either by a stroked-circle technique (`stroke-dasharray` on a circle) or by arc paths with an inner radius; a stroked circle with `stroke-dasharray` per segment is the simplest to make dependency-free and is the chosen approach — each segment is a `<circle>` with the same radius, a `stroke-dashoffset` rotating it to its start, and a dash pattern of `segmentLength gap`.

### Palette
Reuse the categorical palette pattern from `SessionComparisonChart.tsx` (`SERIES_PALETTE` + cyclic `colorFor(index)`). To avoid duplicating the array, lift it into a small shared module (e.g. `lib/palette.ts`) and have both the comparison chart and the new donut import it, or — to keep the change minimal and avoid touching the comparison chart — copy the same palette locally in the donut component. **Decision:** lift to a shared `categoricalColor(index)` helper so slice and legend colors stay consistent and there is one source of truth; update `SessionComparisonChart.tsx` to import it (behavior-preserving, same colors/order).

### Hover detail: accessible tooltip
Each slice is focusable (`tabIndex`, `role`/`aria-label`) and reveals detail on both hover and keyboard focus so the interaction is not mouse-only. The detail text (label, count, percentage) is shown via a small tooltip element positioned near the chart (or a live "active slice" caption below the donut). A caption/active-region below the chart is simpler and robust than absolute-positioned floating tooltips and reads well for keyboard users; a lightweight hover tooltip may layer on top. The legend rows are also hoverable/focusable and highlight their slice, reusing the same active-entry state.

### Percentages and formatting
Percentage = `count / total`. Reuse `formatPercent` from `lib/format.ts` (it takes a fraction and multiplies by 100). Counts render with `toLocaleString()` as today. Guard `total === 0` via the empty state (no slices drawn).

### Component shape
Introduce a `DonutBreakdownChart` (or rework `BreakdownTile`) taking the same props the tile has today: `title`, `entries: {key, count}[]`, `formatKey`. `DashboardPage.tsx` keeps passing `data.assets.by_category` / `by_sector` and `humanize`. Same card styling (`rounded-lg border border-slate-200 bg-white p-6 shadow-sm`).

## Risks / Trade-offs

- **Many small slices** (sectors can be numerous, some with count 1): the palette cycles after 8 colors, and thin slices are hard to hover. Mitigation: legend carries the authoritative color→label mapping and is itself hoverable/focusable, so detail is reachable even for a sliver; ordering stays largest-first as the backend returns it.
- **`no sector` sentinel key** already flows through `humanize`; it renders as a normal slice/legend entry — acceptable and consistent with today's list.

## Migration Plan

None — pure frontend swap of a presentational component. No data or API changes.

## Open Questions

None.
