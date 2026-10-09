## Context

See proposal.md — Why. The asset-universe table lives in `frontend/src/pages/assets/AssetsPage.tsx`, where each row is rendered by the `AssetRow` component and already shows an `EligibilityBadge`. The `Asset` type (`frontend/src/types/api.ts`) already carries `alpaca_symbol: string | null`, mirroring the backend `AssetRead` schema. The backend's `_universe_summary` already treats `alpaca_symbol is None` as the definition of an "unpriceable listing," so the UI needs no new data or signal — only to render it.

## Goals / Non-Goals

**Goals:**
- Make it visible at a glance, per asset row, which assets are not tradable on Alpaca (null `alpaca_symbol`), reusing the exact signal the AI universe-evaluation panel reports.

**Non-Goals:**
- No filter/toggle to show only not-tradable assets (deliberately deferred — badge only).
- No dedicated table column, no sorting by tradability.
- No backend, API, schema, or migration change.
- No auto-resolution/replacement of the flagged listings.

## Decisions

- **Badge, not a column.** Render a small warning-style badge ("Not on Alpaca") inside the existing Eligibility cell's row area, next to `EligibilityBadge`, only when `asset.alpaca_symbol === null`. A badge keeps the table width unchanged and visually pairs the tradability signal with the other per-row status chip. Alternative considered — a dedicated "Tradable" column — was rejected to avoid widening the already-`min-w-[900px]` table and because only a minority of rows carry the flag.
- **Amber/warning palette, distinct from eligibility.** Eligibility already uses emerald (eligible) / red (not eligible). The not-tradable badge uses an amber palette so it reads as a separate, orthogonal concern (an eligible asset can still be untradable on Alpaca). A tooltip (`title`) explains it is a foreign/unpriceable listing to replace with a US listing/ADR, matching the existing `EligibilityBadge` tooltip pattern.
- **Null check only.** "Not tradable" ⇔ `alpaca_symbol === null`. Empty string is not a value the backend produces; treat only `null` (and `undefined`, defensively) as not tradable.

## Risks / Trade-offs

- [Legacy rows never re-verified keep a null `alpaca_symbol` and would be flagged] → This is correct behavior: those rows genuinely have no verified Alpaca symbol, which is exactly what the panel asks the operator to resolve. No mitigation needed.
- [Badge adds visual noise if many rows are untradable] → Acceptable; the whole point is to surface them, and in practice the flagged set is small (the panel reported 16).
