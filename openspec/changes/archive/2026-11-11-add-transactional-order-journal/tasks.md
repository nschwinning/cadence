## 1. Broker client order ids

- [x] 1.1 Add `client_order_id` to `Order`; send it in `AlpacaBroker.submit_order`; add `get_order_by_client_id` to the `Broker` protocol, `AlpacaBroker` (`GET /v2/orders:by_client_order_id`, 404 → `None`) and `StubBroker` (stub rejects a duplicate client id); verify with broker unit tests (payload carries the id, lookup found/not found, stub duplicate rejected).

## 2. Journal

- [x] 2.1 Add the `BrokerOrder` model in `cadence/orders/models.py` and an Alembic migration for `broker_orders` (unique client id, owner index, partial unresolved index); verify upgrade/downgrade round-trip on a scratch DB and drop `cadence_test`.
- [x] 2.2 Implement `orders/journal.py` (independent-session writes: create intent, update after submit, mark refused / not_submitted / resolved; `mark_booked(db, client_order_id)` conditional update raising `AlreadyBookedError`); verify with pytest that an intent survives the caller's rollback and that booking twice raises.
- [x] 2.3 Implement `orders/gateway.py` `OrderGateway` (long-only guard via account positions + symbol key, intent → submit with client id → record result, `WouldShortError`); verify with pytest: guard refuses 10 vs held 4 and unheld symbols, allows 4 vs 10, every submit has a journal row, broker exception leaves row `submitted` with error.
- [x] 2.4 Add an architecture test asserting broker `.buy(` / `.sell(` / `submit_order(` calls appear only in `cadence/orders/` and `cadence/broker/`; verify it fails on a planted call and passes after migration of all paths.

## 3. Reconciler

- [x] 3.1 Refactor bot fill booking out of `ExecutionEngine.enter/exit` into reusable booking functions (incl. anomaly paths) and extract a single-trade AI booking helper from `_apply_rebalance_trades`; verify existing engine and AI booking tests still pass.
- [x] 3.2 Implement `orders/reconcile.py` `reconcile_orders(db, broker, owner=None)` with leases, `SKIP LOCKED`, per-record savepoints and bot / AI / admin adapters, returning booked/closed/remaining counts; verify with pytest: rolled-back bot fill booked once, late fill after poll timeout booked, never-received closed out, rejected-with-no-fill closed, partial fill booked for filled qty, still-working left alone, in-lease row untouched, second run books nothing, one failing record does not stop others.

## 4. Strategy bots

- [x] 4.1 Route `ExecutionEngine` orders through a bot `OrderGateway` (context: asset id, reason), mark booked with each booking, leave timed-out orders to reconciliation, catch `WouldShortError` per position; verify engine tests.
- [x] 4.2 Restructure `run_tick`: reconcile first, per-bot try/commit/rollback for flatten and active bots, skip symbols with unresolved rows, `failed` count in `TickResult` + `BotTickResponse`; verify with pytest reproducing the incident (bot B's order rejected → bot A's and the stopped bot's trades persist; next tick does not re-sell the flattened position; endpoint returns 200 with `failed=1`).

## 5. AI portfolios

- [x] 5.1 Give `AIPortfolioExecutor` a session gateway (build, rebalance, close, stop-loss, scope liquidation), add `TradeResult.client_order_id`, mark booked in `_record_trades` / `_apply_rebalance_trades` / other booking paths, turn `WouldShortError` into a non-retried not-executed result; verify existing AI executor/flow tests plus a refused-oversized-sell test.
- [x] 5.2 Reconcile the session's orders at the start of every AI flow that trades; verify with pytest that a rebalance which fails after submitting has its fill booked exactly once by the next run's reconciliation.

## 6. Admin

- [x] 6.1 Route `flatten_orphans` through an admin gateway; add `restore_positions`, `PositionRow.restorable/restore_quantity`, `unresolved_orders`, short-proceeds-adjusted cash check; verify with pytest (short −6 vs Cadence 4 → buy 10, shortfall 6 vs 10 → buy 4, matched/orphan skipped, pending order skipped, closed-market equity skipped, books untouched, cash check excludes short proceeds).
- [x] 6.2 Add `POST /admin/restore-positions` (`{symbol|null}`, extra=forbid) and `POST /admin/reconcile-orders`, extend the account schema (restorable fields, unresolved orders, reported cash + short proceeds); verify endpoint tests.
- [x] 6.3 Frontend: types + hooks; Restore / Restore all with confirmation and outcomes; Unresolved orders card with Reconcile now and result; cash check shows reported cash and excluded short proceeds; verify with vitest (restore confirm/cancel posts symbol only, restore-all null, reconcile result shown, short-proceeds line, rows without action explain status).

## 7. Verification

- [x] 7.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 7.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 7.3 `openspec validate add-transactional-order-journal --strict` passes.
