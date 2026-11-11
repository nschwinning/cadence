## Context

Order submission is currently interleaved with a single database transaction per request/run:

- **Bot tick** (`strategy_bots.service.run_tick` → `engine.ExecutionEngine.enter/exit`) submits
  and polls each order, then books trade/position/cash into the request's session, which
  `get_db` commits once at the end. Any exception rolls everything back while the orders stand.
  The engine also returns `noop` when an order is not filled after ~5 s of polling, leaving a
  live order nobody tracks.
- **AI portfolios** (`ai_portfolio.executor.AIPortfolioExecutor`) submit via `broker.buy/sell`
  and return `TradeResult`s that the flows book later (`_helpers._record_trades`,
  `_apply_rebalance_trades`) and commit at the end of the run. Per-order errors are caught, and
  `paper_trading.service.reconcile_session_orders` re-queries *recorded* non-terminal orders —
  but orders whose recording was rolled back are invisible.
- **Admin flatten** submits directly and books nothing by design.

Nothing checks the account's holdings before a sell, so a sell based on a stale ledger opens a
short. On 2026-11-10 this produced ~$200k of shorts and orphan longs.

Alpaca supports a caller-supplied `client_order_id` (unique per account; a duplicate is
rejected) and `GET /v2/orders:by_client_order_id`.

## Goals / Non-Goals

**Goals:**
- Every Cadence order is durably recorded before submission and booked exactly once.
- Retries cannot double-execute.
- No Cadence sell can exceed the account's holding.
- One bot's failure never affects other bots' records.
- Tools to restore the account to Cadence's books after the incident.

**Non-Goals:**
- Exactly-once across *different* decisions (a later tick deciding to trade again is a new order).
- Attributing the incident's losses to sessions; cancelling orders; automatic cleanup.
- Changing strategy, sizing or rebalance logic.

## Decisions

### D1. `broker_orders` journal table (new `cadence/orders/` package)

Columns: `id` (uuid), `client_order_id` (text, unique), `owner_kind`
(`bot` | `ai_session` | `admin`), `owner_id` (uuid, nullable for admin), `ticker` (Cadence
ticker), `broker_symbol`, `asset_class`, `side`, `quantity`, `purpose` (e.g. `entry`,
`take_profit`, `session_stopped`, `ai_rebalance_sell`, `admin_restore`), `context` (JSONB:
owner-specific booking data, e.g. bot `asset_id`/`reason`, AI `event_id`/`signal_type`),
`state` (`intent` → `submitted` → `resolved`; plus `refused`, `not_submitted`), `broker_order_id`,
`broker_status`, `filled_quantity`, `filled_price`, `error`, `lease_until`, `booked_at`,
`created_at`, `updated_at`. Indexes on `(owner_kind, owner_id)` and a partial index on unbooked,
unresolved rows. One Alembic migration. *Alternative:* columns on `BotTrade`/`PaperTrade` —
rejected: those rows only exist after booking, which is exactly what can be lost.

### D2. Independent journal sessions

The gateway writes and updates journal rows through its **own short-lived DB session** (a fresh
`SessionLocal()` per write, committed immediately), never the caller's session. So the intent
row is durable before the broker call and survives the caller's rollback. The caller marks the
row booked through *its* session (`orders.journal.mark_booked(db, client_order_id)`), in the same
transaction as its ledger writes, using a conditional `UPDATE … WHERE booked_at IS NULL`; zero
rows updated raises `AlreadyBookedError` (the reconciler got there first), which the caller
treats as "do not book" by rolling back that unit.

### D3. `OrderGateway` — the only way to submit

`OrderGateway(broker, owner_kind, owner_id, lease=…)` exposes `buy(...)`/`sell(...)` with the
`Broker` signatures plus `purpose` and `context`. Steps: (1) for a sell, read
`broker.get_positions()` and match by `admin.service.symbol_key`; if held < qty − ε → write a
`refused` row and raise `WouldShortError(BrokerError)`; (2) insert `intent` row with a fresh
`client_order_id` (`cad-<owner_kind[0]>-<uuid4 hex>`, ≤ 48 chars) and `lease_until = now + lease`;
(3) `broker.submit_order(Order(..., client_order_id=...))`; (4) update row to `submitted` with
broker id/status/fill, or record the error (a broker exception → `error` set, state stays
`submitted` so reconciliation checks whether Alpaca actually received it); (5) return the
`Order` (carrying `client_order_id`). The AI executor and bot engine take a gateway instead of a
raw broker for orders (they keep the raw broker for quotes/polls). Admin uses a gateway with
`owner_kind="admin"`. A grep-based test asserts `.buy(`/`.sell(`/`submit_order(` on a broker
occurs only inside `cadence/orders/` and the broker package.

Leases: bots 2 minutes (a tick's work per bot is seconds), AI runs 30 minutes, admin 1 minute.

### D4. Broker support for client order ids

`Order` gains `client_order_id: str | None`. `AlpacaBroker.submit_order` sends it;
`AlpacaBroker.get_order_by_client_id(id) -> Order | None` calls
`GET /v2/orders:by_client_order_id` (404 → `None`). The `Broker` protocol and `StubBroker` gain the
method; the stub rejects a duplicate client id like Alpaca.

### D5. Reconciler (`orders.reconcile.reconcile_orders(db, broker, owner=None)`)

Selects rows with `booked_at IS NULL`, state in (`submitted`, `intent`), `lease_until < now`,
optionally filtered by owner, `FOR UPDATE SKIP LOCKED`. For each: look up by client id →
- not found → `not_submitted`, resolved, nothing booked;
- terminal with `filled_quantity > 0` (filled, or partially filled then cancelled/expired) →
  book via the owner's booking adapter, mark booked, resolved;
- terminal with no fill (rejected/cancelled/expired) → resolved, nothing booked;
- still working → leave (state `submitted`, updated broker status).

Booking adapters: **bot** → the engine's fill-booking primitives refactored out of
`enter`/`exit` (`book_entry_fill`, `book_exit_fill`): an entry creates the position (asset id from
context) and debits cash; an exit for a position that still exists realises P&L, credits cash,
removes it; an exit whose position is gone (or a second entry while a position exists) is booked
as a trade with the cash effect only and logged as an anomaly. **AI session** → the existing
`record_trade` + `record_closed_position` + `apply_fill_to_ledger` sequence (extracted from
`_apply_rebalance_trades` into a single-trade helper), signal type `<context signal>_reconciled`,
event id from context. **Admin** → mark booked only. Each record is processed in its own
savepoint; a failure is logged and the next record continues. Returns counts
(booked / closed / remaining).

Call sites: start of `run_tick` (all owners); start of every AI flow that trades (that session);
`POST /admin/reconcile-orders` (all). The existing AI `reconcile_session_orders` stays for fill
price/status updates of already-recorded trades.

### D6. Tick isolation

`run_tick` becomes: reconcile → for each stopped bot to flatten, then each active bot: process
inside `try`, `db.commit()` on success, `db.rollback()` + log + `failed += 1` on exception →
settle orchestrator capital → commit. `TickResult`/`BotTickResponse` gain `failed`. The kill-switch
and value-point writes stay inside the bot's unit. Before deciding a bot's orders, symbols with an
unbooked, unresolved journal row for that bot are excluded from entries and exits for this tick.
The engine's poll timeout now leaves the row `submitted` (reconciled later) instead of silently
dropping it. `WouldShortError` on an exit/flatten is caught per position: position unchanged,
warning logged.

### D7. AI executor

`AIPortfolioExecutor` receives a gateway (`owner_kind="ai_session"`, owner = session id,
context = event id + signal prefix). `TradeResult` gains `client_order_id`; the booking helpers
call `mark_booked` for each executed result in the run's transaction. A `WouldShortError` becomes
a not-executed `TradeResult` (reason "Refused: would sell more than the account holds") and is not
retried. Each AI flow calls `reconcile_orders(db, broker, owner=session)` before trading.

### D8. Admin

`admin.service` gains `restore_positions(db, broker, symbol=None)` mirroring `flatten_orphans`
(recompute; eligible = `shortfall` or `short` without pending order; qty = cadence − broker; equity
market gate; buy via admin gateway; per-symbol outcomes), `unresolved_orders(db)` for the
overview, and the cash check's `short_proceeds` = Σ |market_value| of positions with negative
quantity, `account_cash = reported cash − short_proceeds`. `PositionRow` gains `restorable` and
`restore_quantity`. Router: `POST /admin/restore-positions {symbol|null}`,
`POST /admin/reconcile-orders`. Frontend: Restore / Restore all with confirmation, outcomes,
"Unresolved orders" card with Reconcile now, cash check shows reported cash and excluded proceeds.

## Risks / Trade-offs

- **Extra broker call per sell** (positions read for the guard) → acceptable at tick/rebalance
  volumes; one `get_positions` per gateway call.
- **Guard vs shared symbols**: the guard checks the whole account's holding, not the owner's
  share; it prevents shorts, while per-owner correctness remains the ledgers' job.
- **Reconciler vs a slow owner**: protected by leases plus the conditional `mark_booked`; in the
  rare lost race the owner's unit rolls back and the reconciler's booking stands.
- **Independent sessions** add connections per order → small pool usage; sessions are closed
  immediately.
- **Incident cleanup** depends on the operator using Restore/Flatten; losses from the repeated
  trades remain an unattributed account difference.

## Migration Plan

1. Alembic migration creating `broker_orders` (verify upgrade/downgrade on a scratch DB).
2. Deploy with the bot tick still paused; open Admin → Reconcile now (no-op on a fresh journal),
   Restore all (buy back shorts/shortfalls), Flatten all orphans; check positions read Matched.
3. Re-enable the bot tick (remove the `BOT_TICK_SCHEDULE` override, `docker compose up -d cron`).
Rollback: revert code; the table can stay (downgrade drops it).

## Open Questions

None.
