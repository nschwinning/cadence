## Why

The unified Portfolios list shows each session's performance and portfolio definition, but not how long the portfolio has been running. Age is important context when comparing sessions: a +5% return over three days and a +5% return over three months are very different outcomes, and the list currently gives no at-a-glance sense of how mature each session is.

## What Changes

- Add a **portfolio age** indicator to each row of the unified Portfolios list, derived from the session's creation time (`created_at`), shown as a compact human-readable duration (e.g. `5d`, `3w`, `2mo`, `1y`) with the exact creation date available on hover.
- Add a reusable `formatAge` helper to the frontend formatting utilities so the age string is produced deterministically and is unit-testable.
- Frontend-only. No backend change: `created_at` is already exposed on the session read model consumed by the list. No migration, no new endpoint, no schema change.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `app-shell`: The unified Portfolios list requirement gains the portfolio age as a per-row attribute presented alongside the existing status, capital, trade count, value, and P&L columns.

## Impact

- Frontend: `frontend/src/pages/paper-trading/PaperTradingPage.tsx` (new age cell/column per row), `frontend/src/lib/format.ts` (new `formatAge` helper), co-located Vitest coverage for the helper and the list row.
- No backend, API, database, or dependency impact; relies on the `created_at` field already present on the session read model.
