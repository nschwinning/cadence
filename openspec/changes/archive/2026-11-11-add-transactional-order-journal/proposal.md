## Why

Since 2026-11-10 09:35 ET the strategy-bot tick failed every 5 minutes, and each failed tick
still left real orders behind: the tick submits orders to Alpaca as it goes but records them
only when its single database transaction commits at the end, so the error rolled back the
records while the orders stood. The next tick re-sent the same sells (stopped-bot flattening,
exits) and buys, building roughly $200k of **short positions** and untracked **orphan longs** in
the shared paper account — although Cadence is long-only. The same gap exists, more narrowly, in
AI-portfolio runs (orders recorded only at the run's commit) and in the bot engine's poll timeout
(an order still working after ~5 s is forgotten and may fill later unrecorded). Cadence needs a
guarantee that every order it sends is recorded, that a retry can never trade twice, and that it
can never sell shares the account does not hold.

## What Changes

- **Write-ahead order journal**: before any order is submitted, Cadence durably records the
  intended order (owner, symbol, side, quantity, purpose) with a unique **client order id**, in a
  commit independent of the caller's transaction. The id is sent to Alpaca, which refuses a
  second order with the same id, so a retry cannot double-trade. The caller books the fill into
  its ledger and marks the journal entry booked in the same transaction.
- **Order reconciliation**: journal entries left unbooked (crash, rollback, poll timeout, late
  fill) are resolved against Alpaca by client order id and their fills booked into the owning
  bot or AI portfolio exactly once; entries Alpaca never received are closed out. Reconciliation
  runs at the start of every bot tick and AI-portfolio run, and on demand from the Admin page.
- **One order gateway for every order path**: strategy-bot entries/exits and stopped-bot
  flattening, AI-portfolio build/rebalance/close/stop-loss/scope liquidation, and Admin actions
  all submit through it.
- **Long-only guard**: the gateway refuses any sell larger than the quantity the account
  actually holds for that symbol — no order is sent, the refusal is reported to the caller.
- **Bot tick isolation**: each bot is processed and committed on its own; one bot's failure
  (including a broker rejection) is logged and no longer fails or rolls back the others. A bot
  with an unresolved journal entry for a symbol does not trade that symbol until it is resolved.
- **Admin page**: a confirmed **Restore** action buys back shortfalls and shorts up to exactly
  the quantity Cadence tracks (cleaning up the current account); an **Unresolved orders** section
  lists unbooked journal entries with a "Reconcile now" button; orphan flattening goes through
  the gateway.
- **Migration**: one new table for the journal. No new environment variables.

## Capabilities

### New Capabilities
- `order-journal`: durable, idempotent recording of every broker order Cadence sends, its
  reconciliation and booking, and the long-only sell guard.

### Modified Capabilities
- `strategy-bots`: per-bot isolation and commit in the tick; no trading on a symbol with an
  unresolved order.
- `ai-paper-trading`: AI-portfolio orders go through the journal; reconciliation before each run.
- `broker-account-admin`: restore action, unresolved-orders view and reconcile-now action.
- `app-shell`: the Admin page shows the restore action and the unresolved-orders section.

## Impact

- Backend: new `cadence/orders/` package (journal model, gateway, reconciler), Alembic migration
  for `broker_orders`; `broker/` gains client order ids (`Order.client_order_id`, Alpaca submit +
  lookup by client id, stub support); `strategy_bots/engine.py` + `service.run_tick`;
  `ai_portfolio/executor.py`, `_helpers.py` booking, flows and `stop_loss.py`;
  `paper_trading/service.py` scope liquidation; `admin/service.py` + router.
- Frontend: Admin page restore action, unresolved-orders section, types/hooks.
- Operational: until deployed, keep the bot tick paused and set Alpaca `no_shorting` on the
  account; after deploy, use Restore + Flatten to bring the account back in line with Cadence.
- Out of scope: attributing the losses from the repeated trades to any session (they remain an
  account-level difference), cancelling orders, automatic cleanup.
