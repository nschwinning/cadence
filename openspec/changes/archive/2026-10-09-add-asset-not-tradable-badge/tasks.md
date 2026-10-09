## 1. Implement the not-tradable badge

- [x] 1.1 In `frontend/src/pages/assets/AssetsPage.tsx`, add a `NotTradableBadge` (or inline equivalent) rendered only when `asset.alpaca_symbol == null`: an amber/warning-style chip reading "Not on Alpaca" with a `title` tooltip explaining it is a foreign/unpriceable listing that can't be traded and should be replaced with a tradable US listing/ADR. Verify by running the app/typecheck that the component compiles and no badge is produced when `alpaca_symbol` is non-null.
- [x] 1.2 Render the badge inside `AssetRow` next to the existing `EligibilityBadge` (same cell/area), so tradability reads as a status chip distinct from eligibility. Verify via `npm run build` that the table layout still compiles without widening/new columns.

## 2. Tests

- [x] 2.1 In `frontend/src/pages/assets/AssetsPage.test.tsx`, add a test asserting the "Not on Alpaca" badge renders for an asset with `alpaca_symbol: null` and is absent for an asset with a non-null `alpaca_symbol`. Verify with `npx vitest run`.

## 3. Verify gates

- [x] 3.1 Run `cd frontend && npm run typecheck && npx vitest run && npm run build` and confirm all three pass.
