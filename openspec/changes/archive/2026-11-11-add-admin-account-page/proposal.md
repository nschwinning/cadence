## Why

AI portfolios, strategy bots and bot orchestrators all trade inside **one shared Alpaca paper
account**, but Cadence never shows that account. When the account and Cadence's own books
drift apart — cash already spent elsewhere, or shares held that no Cadence session owns — the
first visible symptom is a broker rejection (on 2026-11-10 every bot tick after 09:35 ET failed
with `403 Forbidden` on `POST /v2/orders`). The operator needs to see the account's real cash
next to what Cadence believes it has committed, and needs a safe way to sell positions that do
not belong to Cadence so they stop tying up cash.

## What Changes

- New **Admin** page in the sidebar (the System page stays a pure health check):
  - **Account**: live cash, buying power, and total portfolio value from the broker.
  - **Cash check**: the cash Cadence believes is committed (each active AI portfolio's cash,
    each active bot's cash, each active orchestrator's free capital, and stopped orchestrator
    bots whose cash has not yet been returned), its total, the account's cash, and the
    difference — with a warning when Cadence has committed more than the account holds.
  - **Open orders**: the account's open orders.
  - **Positions comparison**: per symbol, the broker quantity, the quantity Cadence tracks
    (all AI-portfolio ledgers + all bot positions, including stopped bots not yet flattened),
    and the **orphan (excess) quantity** = broker − Cadence; shortfalls (Cadence tracks more
    than the account holds) and short positions are flagged but not actionable.
- **Flatten orphan positions**: per row or "flatten all", each behind a confirmation dialog.
  Only the excess quantity is sold, so a symbol shared with Cadence is trimmed, never wiped.
  Symbols with open orders are skipped. The server **recomputes** orphans at execution time
  and never trusts quantities sent by the browser. Equity orphans are only sold while the
  equity market is open; crypto any time. Orphan sells are never written to any Cadence
  ledger.
- New backend endpoints: a read-only account overview and a flatten action. No database
  migration, no new environment variables, no extra authentication (same trust model as the
  existing stop/archive actions — confirmation dialog only).

## Capabilities

### New Capabilities
- `broker-account-admin`: the broker account overview (account figures, cash check, open
  orders, positions comparison with orphan detection) and the orphan-flattening action.

### Modified Capabilities
- `app-shell`: adds the Admin navigation entry and page.

## Impact

- Backend: new `cadence/admin/` service package (reconciliation + flatten), new
  `api/routers/admin.py`, new schemas in `api/schemas.py`; reads `broker.get_account_info`,
  `get_positions`, `get_open_orders`, `is_market_open`, and submits sells via `broker.sell`.
  Reads (never writes) AI-portfolio ledgers, bot sessions/positions and orchestrators.
- Frontend: new `pages/admin/AdminPage.tsx`, `api/admin.ts`, TS types, sidebar entry + route.
- No migration, no dependency, no env/compose change. Out of scope: fixing the tick's
  all-or-nothing failure on a broker rejection (separate change), cancelling orders, buying
  back shortfalls, covering shorts, scheduled/automatic flattening, dashboard tile.
