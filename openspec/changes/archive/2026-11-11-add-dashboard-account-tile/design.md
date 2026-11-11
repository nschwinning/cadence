## Context

`GET /api/v1/admin/account` (Admin page) already returns everything the tile needs:
`cash_check.difference` (free capital = account cash excluding short-sale proceeds − committed),
`cash_check.committed_total`, `cash_check.account_cash`, `cash_check.short_proceeds`, and
`positions[]` with `status === 'short'`. `useAdminAccount` (`api/admin.ts`) polls it every 60 s.

## Goals / Non-Goals

**Goals:** a dashboard tile with free capital, low/none/short warnings and a link to Admin.

**Non-Goals:** new endpoints; configurable thresholds; orphan/unresolved-order warnings (they
stay on the Admin page); any change to the dashboard overview payload.

## Decisions

1. **Reuse the Admin query** rather than adding fields to `/dashboard/overview`: the data and
   its semantics already exist and are tested; sharing the React Query key means the Admin page
   and the dashboard reuse one cache entry. Cost: three broker reads per minute while the
   dashboard is open — negligible. *Alternative:* extend the overview — rejected (duplicates the
   reconciliation logic in another payload).
2. **Threshold** `LOW_CAPITAL_THRESHOLD_USD = 1_000` in the tile module, matching the minimum
   capital of the bot and AI-portfolio build forms (`min={1000}`). Free capital ≤ 0 → red
   (takes precedence over amber).
3. **Short positions** = rows with `status === 'short'`; count from the rows, value from
   `cash_check.short_proceeds` (the absolute short market value the backend already computes).
4. **Placement**: a "Broker account" `ScopeBand` directly after the "Portfolio value" band
   (no freshness badge: the shared "Live" chip's tooltip is about marking positions to market,
   which does not describe an account balance) (account-wide, so outside the range-scoped performance band).
   Rendered regardless of whether any session exists.
5. **Component**: `components/dashboard/AccountStateTile.tsx`, card styling like the AI cost
   panel; warnings as `role="alert"` blocks (red) / `role="note"` (amber); loading text while
   pending; broker-unavailable when the query errors or `broker_available` is false.

## Risks / Trade-offs

- The Admin overview also lists positions/orders — slightly more payload than the tile needs;
  acceptable at this scale.
- If the broker is slow, the tile loads after the rest of the dashboard (independent query).

## Migration Plan

Frontend only; ships with the normal deploy.

## Open Questions

None.
