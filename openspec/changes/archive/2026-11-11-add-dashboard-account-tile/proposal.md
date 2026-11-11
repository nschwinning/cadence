## Why

Every AI portfolio, strategy bot and orchestrator draws on one shared Alpaca paper account,
but the dashboard never shows how much of it is still free. Deploying a new bot or portfolio
without spare capital — or while the account carries short positions, as after the
2026-11-10 incident — leads to broker rejections that are only diagnosable on the Admin page.
The operator should see the account's headroom and any red flags at a glance on the dashboard.

## What Changes

- New **Broker account** section on the dashboard with one tile showing the **free capital**
  available for new bots and portfolios: the account's cash excluding short-sale proceeds
  minus everything Cadence has committed (the Admin cash check's difference), with the
  committed total and account cash as context.
- Warnings on the tile:
  - **amber** when free capital is below **$1,000** (the smallest capital a new bot or AI
    portfolio can be built with);
  - **red** when free capital is zero or negative (nothing left — new deployments will be
    rejected);
  - **red** when the account holds **short positions**, naming how many and their value.
- The tile links to the Admin page; when the broker is unavailable it says so instead of
  showing figures.
- Frontend-only: reuses the existing `GET /api/v1/admin/account` data. No backend, migration
  or environment change.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `app-shell`: adds the dashboard broker-account tile requirement.

## Impact

- Frontend: new `components/dashboard/AccountStateTile.tsx` (+ test), rendered by
  `pages/dashboard/DashboardPage.tsx`; reuses `useAdminAccount` from `api/admin.ts`.
- No backend, API, migration or env changes.
