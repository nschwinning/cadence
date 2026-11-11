## 1. Tile

- [x] 1.1 Create `components/dashboard/AccountStateTile.tsx` using `useAdminAccount`: free capital (`cash_check.difference`) with committed total and account cash, link to `/admin`, amber warning below $1,000, red "no capital left" at ≤ 0, red short-positions warning (count of `status === 'short'` rows + `short_proceeds`), broker-unavailable and loading states; verify with vitest covering healthy (no warning), low (amber), none (red), shorts (red with count and value), both reds together, unavailable, link target.
- [x] 1.2 Render it in `DashboardPage.tsx` in a "Broker account" band after "Portfolio value", independent of range/selection; verify with a dashboard page test that the band renders and the tile's figures do not change when the range changes.

## 2. Verification

- [x] 2.1 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 2.2 `openspec validate add-dashboard-account-tile --strict` passes.
