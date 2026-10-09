## Why

Cadence trades against Alpaca with market orders, but the paper-trading engine
charges a flat `TRANSACTION_COST_USD = 1.0` per executed fill regardless of asset
class. That does not match Alpaca's real fee schedule:

- **US equities/ETFs** are commission-free for market orders. The only equity cost
  is market-order slippage, which is already reflected in the fill price (the
  executor sizes and records against actual fills), plus negligible sub-cent
  SEC/FINRA fees on sells. A flat $1/trade is a pure, unrealistic drag that would
  not exist live.
- **Crypto** is *not* free — Alpaca charges a percentage taker fee (~0.25% at the
  base tier) on the trade's notional, not a flat amount.

The flat fee is a holdover from the original trading-bot fusion. It distorts
paper-trading P&L: it over-charges every equity trade and mis-shapes crypto costs
(flat instead of notional-scaled). This change replaces it with an asset-class-aware
model so reported fees, net valuation, and the cost KPIs reflect what the strategy
would actually pay on Alpaca.

A direct consequence: once equities are free, the session's **daily average
transaction cost** KPI tile (cumulative fees ÷ snapshot days) collapses toward zero
for equity-only sessions and stops being an informative headline metric. This change
therefore also **exchanges that tile for a daily average orders tile** (the session's
average number of filled orders per snapshot day), which stays meaningful regardless
of the fee model, and records each day's filled-order count in the backend-only
daily-run learning snapshot so offline learning captures trading activity directly.

## What Changes

- **Equities (and any non-crypto class): $0 transaction fee.**
- **Crypto: a percentage fee on executed notional** (`filled_price × quantity`,
  falling back to quoted price when unfilled), using a new configurable
  `CRYPTO_FEE_PCT` defaulting to `0.0025` (0.25%, Alpaca base-tier taker).
- `record_trade` becomes asset-class-aware: callers pass the trade's `asset_class`
  so the single fee choke point can charge `0` for equities and `CRYPTO_FEE_PCT ×
  notional` for crypto into the existing `paper_trading_sessions.total_fees`.
- The executor's cash-buffer `fee_reserve` is recomputed under the new model: no
  reserve for equities (slippage is still covered by `REBALANCE_CASH_BUFFER_PCT`),
  a notional-percentage reserve for crypto candidates.
- The dashboard projected-fee estimate is revised off the flat-per-trade
  assumption.
- The flat `TRANSACTION_COST_USD` setting is retired in favor of `CRYPTO_FEE_PCT`
  (decision and migration path documented in design.md).
- The session KPI summary's `daily_avg_transaction_cost` figure is **replaced by**
  `daily_avg_orders` (total recorded orders ÷ number of daily value snapshots,
  unavailable until the first snapshot) — through the KPI dataclass, the read
  schema, the router mapping, and the TypeScript type.
- The session-detail **daily-average-transaction-cost tile is exchanged for a
  daily-average-orders tile** (same grid slot, keeping the ten-tile / two-row
  layout; shown as a number, not a currency amount), and the transaction-fees
  tile's stale `$1 per executed trade` hint is corrected to the new model.
- The backend-only **daily-run learning snapshot** document records each day's
  filled-order count (`orders_count`) alongside the day's orders.
- **Historical fees are restated** (one-time data migration) so existing sessions
  reflect the new model: every session's `total_fees` is recomputed from its trade
  ledger (equity → $0, crypto → `CRYPTO_FEE_PCT × notional`, replacing the retired
  flat $1/trade), and each session's recorded value snapshots are re-derived so
  historical valuations and daily P&L reflect the corrected (lower) fees.

No DB **schema** change: `total_fees`, the value-snapshot columns, and the learning
snapshot's JSONB `document` keep their shape. There is a one-time **data-only**
Alembic migration that restates recorded fee amounts and re-derives affected value
snapshots (no table/column added or removed). The other interface changes are one
KPI field rename and one UI tile swap.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ai-paper-trading`: the per-trade transaction-cost model (asset-class-aware fees
  at trade recording, the executor cash-buffer fee reserve, and dashboard fee
  estimation) replaces the flat per-trade fee; the live KPI summary swaps the daily
  average transaction cost for a daily average orders metric; the daily-run learning
  snapshot additionally records each day's filled-order count.
- `app-shell`: the session-detail performance KPI tile grid exchanges the daily
  average transaction cost tile for a daily average orders tile (unchanged ten-tile,
  two-row layout).

## Impact

- **Settings** (`config.py`): add `CRYPTO_FEE_PCT` (default `0.0025`); retire
  `TRANSACTION_COST_USD`.
- **`paper_trading/service.py`** `record_trade`: new `asset_class` parameter;
  asset-class-aware fee into `total_fees`.
- **`ai_portfolio/service.py`**: thread the in-scope asset class to each
  `record_trade` call (build, rebalance, stop-loss, scope-change close).
- **`ai_portfolio/executor.py`**: recompute the cash-buffer fee reserve under the
  new model.
- **`dashboard/service.py`**: revise the projected-fee estimate.
- **`paper_trading/service.py`** `session_kpis` / `SessionKpis`: replace
  `daily_avg_transaction_cost` with `daily_avg_orders` (reusing the existing
  `count_session_trades` helper over the snapshot-day denominator).
- **`api/schemas.py`** + **`api/routers/paper_trading.py`**: rename the KPI read
  field and its router mapping.
- **`ai_portfolio/service.py`** `_build_run_document`: add `orders_count` to the
  daily-run learning snapshot document.
- **`frontend/src/types/api.ts`** + **`PaperTradingSessionPage.tsx`**: swap the TS
  KPI field and the session-detail tile (and fix the transaction-fees tile hint).
- **Migration** (`migrations/versions/`): one-time **data-only** Alembic revision
  (new head off the current head) that restates each session's `total_fees` under
  the new model and re-derives affected value snapshots; no schema change.
- **Tests**: update fee/valuation/KPI/cash-buffer expectations; add crypto-pct and
  equity-zero fee tests; update the KPI API/service tests and the session-page
  vitest for the tile swap; assert `orders_count` in the assembled daily-run
  document; add a backfill test over a mixed equity/crypto session (recomputed
  `total_fees`, lifted snapshots, recomputed daily P&L).
- One-time data-only migration (no DB schema change); one KPI field rename and one
  UI tile swap.
