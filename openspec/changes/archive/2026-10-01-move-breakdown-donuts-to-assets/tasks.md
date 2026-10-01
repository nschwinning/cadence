## 1. Donut component: drop the legend

- [x] 1.1 In `frontend/src/components/dashboard/BreakdownTile.tsx`, remove the `<ul>` legend block (color swatch + label + count + percentage rows). Keep the donut SVG, the center overlay (total by default; active slice's label/count/percentage on hover/focus), the focusable `aria-label`-bearing slices, and the "No data yet" empty state. Center the donut within the card now that the legend is gone. Verify: component still renders slices + center total + empty state, with no legend list.

## 2. Remove the donuts from the Dashboard

- [x] 2.1 In `frontend/src/pages/dashboard/DashboardPage.tsx`, remove the two `<BreakdownTile>`s (and the `BreakdownTile` import + the now-unused `humanize` helper if it moves to the Assets page). Keep all StatTiles and the health indicator. Verify: dashboard renders its stat tiles and no longer shows "By category" / "By sector".

## 3. Add the donuts to the Assets page

- [x] 3.1 In `frontend/src/pages/assets/AssetsPage.tsx`, fetch breakdowns via `useDashboardMetrics()` and render the by-category and by-sector donuts using `BreakdownTile`, passing `data.assets.by_category` / `by_sector` and a `humanize` label helper. Lay them out as two equal-sized tiles side by side (`grid grid-cols-1 gap-4 sm:grid-cols-2`), stacking on narrow viewports. Render nothing (or leave the area empty) until metrics data is present. Verify: Assets page shows two equal-sized donut tiles for category and sector.

## 4. Tests + verification

- [x] 4.1 Update `frontend/src/components/dashboard/BreakdownTile.test.tsx`: remove legend-specific assertions; assert slices, center total, hover/focus detail, and the empty/zero-total states still hold, and that no persistent legend list is rendered.
- [x] 4.2 Update `frontend/src/pages/dashboard/DashboardPage.test.tsx`: no longer expect "By category" / "By sector" tiles; keep the stat-tile assertions (restore any fixture value changed only to avoid the donut-center collision).
- [x] 4.3 Add/adjust the Assets page test to assert the two donut tiles render from mocked dashboard metrics.
- [x] 4.4 Frontend: `npm run typecheck && npx vitest run && npm run build` all green.
- [x] 4.5 `openspec validate move-breakdown-donuts-to-assets --strict` passes.
