## Why

The AI universe-evaluation panel tells the operator to "resolve symbol/mapping issues so the foreign/unpriceable listings are tradable or replace them with equivalent tradable listings," but the asset-universe list gives no way to tell *which* assets those are. The operator has to cross-reference the panel's ticker list by hand. The data needed to flag them already exists on every asset row (`alpaca_symbol`), so the gap is purely that the list doesn't show it.

## What Changes

- In the asset-universe list table on the Assets page, each asset row whose `alpaca_symbol` is null SHALL display a small "Not on Alpaca" badge (warning/amber style) alongside the existing eligibility badge, with a tooltip explaining it is a foreign/unpriceable listing that can't be traded and should be replaced with a US listing/ADR.
- Rows whose `alpaca_symbol` is non-null show no such badge (unchanged appearance).
- Display-only, frontend-only: `alpaca_symbol` is already exposed on the backend `AssetRead` schema and the frontend `Asset` type. No backend, API, or database change.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `app-shell`: the "Asset management views" requirement gains behavior requiring the asset list to visually flag assets that are not tradable on Alpaca (null `alpaca_symbol`).

## Impact

- Frontend only: `frontend/src/pages/assets/AssetsPage.tsx` (new badge rendered in the asset row next to `EligibilityBadge`) and its co-located test `AssetsPage.test.tsx`.
- No backend, no `api/schemas.py`, no DB migration, no new dependencies.
- Verify gates: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
