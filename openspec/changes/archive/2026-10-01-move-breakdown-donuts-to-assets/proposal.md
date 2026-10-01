## Why

The asset-composition donut charts ("By category" / "By sector") live on the Dashboard, but they describe the asset *universe* — the same thing the Assets page is about — so that is where a user looking at composition expects them. Each donut also carries a per-slice color→label legend that duplicates the hover/focus detail and widens the tile unevenly, making the two tiles different sizes.

## What Changes

- Move the two asset-composition donut tiles ("By category" and "By sector") off the **Dashboard** and onto the **Assets** page.
- Remove the per-slice color→label **legend** from each donut. Slice identity is revealed on hover/keyboard-focus only (the existing center overlay + `aria-label` already show the label, exact count, and percentage).
- Render the two donut tiles at **equal size**, side by side (stacking on narrow viewports).
- The donut chart keeps its slices, center total, hover/keyboard-focus detail, and "No data yet" empty state.
- Frontend-only. No backend, schema, API, or migration change. The Assets page reuses the existing `/dashboard/metrics` read (`useDashboardMetrics`) for the `by_category` / `by_sector` counts.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `app-shell`: the existing "Dashboard asset-composition donut charts" requirement changes — the donut charts move to the Assets page, the mandatory legend is removed (identity is hover/focus-only), and the two tiles are equal-sized.

## Impact

- `frontend/src/components/dashboard/BreakdownTile.tsx` — remove the legend list; keep slices, center total, hover/focus detail, empty state.
- `frontend/src/pages/dashboard/DashboardPage.tsx` — stop rendering the two `BreakdownTile`s (StatTiles unchanged).
- `frontend/src/pages/assets/AssetsPage.tsx` — render the two equal-sized donut tiles, sourcing `by_category` / `by_sector` from `useDashboardMetrics`.
- Tests: `BreakdownTile.test.tsx` (drop legend assertions), `DashboardPage.test.tsx` (no longer expects the breakdown tiles), `AssetsPage` test (now shows them).
- No backend, API, DB, or dependency changes.
