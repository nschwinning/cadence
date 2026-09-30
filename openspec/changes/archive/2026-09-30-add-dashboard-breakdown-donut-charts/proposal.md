## Why

The Dashboard's "By category" and "By sector" breakdowns are ranked text lists of raw counts. A reader cannot see each group's share of the universe at a glance, and there is no way to read an exact value with its percentage. A donut chart with hover makes the composition legible and exposes the precise count and percentage on demand.

## What Changes

- Replace the two Dashboard breakdown tiles ("By category", "By sector"), currently ranked `{key, count}` lists, with **donut (ring) charts**.
- Each slice represents one breakdown entry, sized by its share of the total count; slices are colored from a categorical palette and identified by a legend mapping color → humanized label.
- **Hovering a slice reveals a tooltip** with the humanized label, the exact count, and that group's percentage of the total. Percentages are derived on the client from the counts (no new API data).
- The donut center displays the **total count** across the breakdown.
- Preserve the existing "No data yet" empty state when a breakdown has no entries, and the existing humanized labels.
- No backend, schema, migration, or API change: the chart consumes the existing `by_category` / `by_sector` `{key, count}` arrays.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `app-shell`: The dashboard asset-composition breakdowns are presented as interactive donut charts with per-slice hover detail (label, exact count, percentage) and a legend, instead of ranked count lists.

## Impact

- Frontend only. Affected: `frontend/src/components/dashboard/BreakdownTile.tsx` (reworked into a donut chart, or replaced by a new chart component) and its use in `frontend/src/pages/dashboard/DashboardPage.tsx`. Reuses the inline-SVG chart conventions and categorical palette pattern from `SessionComparisonChart.tsx` and helpers in `lib/format.ts`.
- Introduces the codebase's first pie/donut chart and its first chart hover-tooltip interaction pattern.
- No backend, database, dependency, or configuration changes.
