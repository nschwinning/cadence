## Context

The donut `BreakdownTile` (`frontend/src/components/dashboard/BreakdownTile.tsx`) today renders a flex row: the donut on the left, a color→label legend list on the right. It is used only by `DashboardPage`, which sources `by_category` / `by_sector` from `useDashboardMetrics()` (`/dashboard/metrics`). We want the two donuts on the Assets page instead, without the legend, equal-sized.

## Goals

- Donuts (with center total + hover/focus detail + empty state) appear on the Assets page as two equal-sized tiles.
- No persistent legend.
- Dashboard keeps its StatTiles but no longer shows the donuts.
- Frontend-only; reuse the existing metrics read.

## Decisions

- **Drop the legend from `BreakdownTile` rather than add a prop.** The only consumer is moving and nobody wants the legend, so a `showLegend` toggle would be dead configurability. Remove the `<ul>` legend block; keep the donut, the center overlay, and the `aria-label`-bearing focusable slices so identity stays reachable by hover and keyboard without the list.
- **Equal sizing via a fixed donut box in an equal-width grid.** The donut already renders in a fixed `h-40 w-40` box. With the legend gone, each tile is just that donut centered in the card. Lay the two tiles out in `grid grid-cols-1 gap-4 sm:grid-cols-2` (as the Dashboard did) with equal-width columns and matching card styling so both tiles are identical in size. Center the donut within each card.
- **Source data on the Assets page from `useDashboardMetrics()`.** The assets table is paginated and filtered, so counts cannot be derived reliably client-side; the metrics endpoint already returns authoritative `by_category` / `by_sector` largest-first. Reuse the existing hook — no new endpoint. Handle its pending/error states quietly (the donuts simply do not render until data is present), consistent with how the Dashboard treated them.
- **Keep the `humanize` label helper.** It currently lives in `DashboardPage`. Move/duplicate the small helper to the Assets page (or a shared spot) so labels render the same; keep it minimal.
- **Accessibility unchanged.** Slices remain `role="button"` + `tabIndex={0}` with an `aria-label` carrying label + count + percentage; the center overlay mirrors the active slice. Removing the legend does not remove any accessible path to a slice's identity.

## Risks / Trade-offs

- **No legend means color→label is only discoverable by interaction.** Accepted per the request; the hover/focus detail and center overlay already convey the full label + count + percentage, so colors are decorative rather than load-bearing.
- **Touch devices** reveal detail via tap-focus on a slice; this matches the existing focus behavior and is acceptable for this overview widget.

## Migration / Rollout

Pure frontend edit, no data or API change. The component stays in `components/dashboard/` (name/location unchanged to minimize churn); only its legend is removed and its mount point moves.
