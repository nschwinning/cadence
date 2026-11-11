## Context

All Cadence trading — AI portfolios (`SessionPosition` ledger), strategy bots (`BotPosition`,
`BotSession.cash`) and bot orchestrators (`BotOrchestrator.free_capital`) — shares one Alpaca
paper account. Cadence's ledgers are the source of truth for what each session owns; the broker
is only used to place orders and price positions. Nothing surfaces the account itself, so drift
(cash spent twice, shares bought outside Cadence or left behind by failed bookkeeping) is only
noticed via broker rejections. The `Broker` protocol already exposes `get_account_info`,
`get_positions`, `get_open_orders`, `is_market_open` and `sell`.

## Goals / Non-Goals

**Goals:**
- One read endpoint returning account figures, committed-cash check, open orders and a
  per-symbol positions comparison with orphan classification.
- One action endpoint that sells recomputed orphan quantities, per symbol or all.
- An Admin page rendering both, with confirmation before any sell.

**Non-Goals:**
- Making the bot tick tolerant of one bot's broker rejection (separate change).
- Cancelling orders, buying back shortfalls, covering shorts, auto/scheduled flattening.
- Authentication; persisting an audit table (outcomes are logged instead).
- Any write to Cadence ledgers, trade history or orchestrator pools.

## Decisions

1. **New `cadence/admin/` package** (`service.py` with pure reconciliation + flatten,
   `models.py`-free dataclasses for results) and `api/routers/admin.py` mounted at
   `/api/v1/admin` with `GET /account` and `POST /flatten-orphans` (body `{ "symbol": str | null }`
   — `null` means all). Plain (not cron-guarded) like the existing stop/archive actions.
   *Alternative:* extend `system` — rejected; System is a side-effect-free health probe.

2. **Symbol matching key.** Alpaca reports equities like `BRK.B` and crypto positions like
   `BTCUSD` (orders may use `BTC/USD`), while Cadence ledgers hold `BRK-B` / `BTC-USD`. Compare on
   a normalised key: upper-case with `-`, `/`, `.` removed (`BRKB`, `BTCUSD`). Display the
   broker's symbol. A collision between two real tickers that differ only by separators is not
   possible within the supported universe (US equities + USD crypto pairs).

3. **Asset class of broker positions.** Add an optional `asset_class: AssetClass | None = None`
   to the broker `Position` dataclass, set by `AlpacaBroker._parse_position` from Alpaca's
   `asset_class` (the stub leaves it `None` → treated as equity). Needed to decide market-hours
   gating and to pass the right class to `sell`. Additive; existing callers unaffected.

4. **Cadence-tracked quantity** = Σ `SessionPosition.quantity` over **all** AI sessions plus
   Σ `BotPosition.quantity` over **all** bots (any status). Counting inactive owners is
   deliberately conservative: we never call something an orphan that any Cadence record claims.

5. **Classification** with tolerance `ε = 1e-6` (quantities are floats, crypto fractional):
   `short` if broker qty < −ε; else `orphan` if broker − cadence > ε (orphan qty = difference);
   `shortfall` if cadence − broker > ε; else `matched`. Cadence-only symbols (broker holds
   nothing) appear as `shortfall` rows. `pending_order` = any open order on the same key;
   `flattenable = orphan and not pending_order`.

6. **Committed cash.** Active (not stopped, not archived) AI session cash = `allocated_capital + total_pnl − total_fees −
   Σ(quantity × avg_cost)` over its ledger — the same identity `compute_session_value` uses, but
   without quotes (cash does not depend on marks). Active bots: `bot.cash`. Active
   orchestrators: `free_capital`. Stopped orchestrator bots with `capital_returned_at IS NULL` (flat or still being flattened):
   `bot.cash` (they still hold money that will flow back to the pool). Manual stopped bots are
   excluded (their leftover cash is no longer committed to anything). Difference = account
   `cash_balance` − committed total; negative → `shortfall: true`.

7. **Flatten execution.** Recompute the comparison inside the request (fresh `get_positions`,
   `get_open_orders`, DB reads); ignore any client quantity. For each target: skip with reason
   (`not_orphan`, `pending_order`, `market_closed`, `not_found`); otherwise
   `broker.sell(symbol, orphan_qty, asset_class=…)` (market; the broker already maps time in force
   for crypto). Catch `BrokerError` per symbol → `failed` with message. Log every outcome at
   INFO/WARNING. No DB writes, so no transaction concerns. Market-hours gate only for equities.

8. **Broker unavailable.** `GET /account` catches `BrokerError` around the broker reads and
   returns `{ broker_available: false, reason }` with empty sections (200), mirroring the
   system-status "always 200" style. `POST` returns 503 when the broker cannot be read.

9. **Frontend.** `api/admin.ts` (`useAdminAccount` query, manual refetch; `useFlattenOrphans`
   mutation invalidating the account query), `pages/admin/AdminPage.tsx` with four `Panel`s
   (Account, Cash check, Open orders, Positions), a confirmation modal reusing the existing modal
   pattern, and an outcome list. Sidebar entry "Admin" after "System" with a new icon; route
   `/admin`.

## Risks / Trade-offs

- **Race with a tick or rebalance** placing an order between recompute and sell → mitigated by
  skipping symbols with open orders and recomputing at execution; a sub-second window remains.
  A Cadence buy that has *filled* but not yet been booked could look like an orphan for that
  instant — the confirmation step plus the 5-minute tick cadence make this unlikely; operators
  should avoid flattening during 09:30–09:40 ET when rebalances run.
- **Ledger drift the other way** (shortfall) is only reported, not repaired.
- **No auth**: anyone reaching the Pi can sell orphans — accepted by the user; confirmation only.
- **Fractional equity orphans** need a market DAY order; Alpaca supports fractional market
  sells, so no special handling.

## Migration Plan

None — no schema change. Deploy with the usual `docker compose up -d --build`; rollback by
reverting the code.

## Open Questions

None.
