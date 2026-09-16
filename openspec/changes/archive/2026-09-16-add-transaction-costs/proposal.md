## Why

Paper-trading sessions currently execute trades for free, so the AI has no
disincentive to churn tiny positions and the reported PnL / portfolio value is
optimistic versus a real Alpaca account that charges per fill. Modeling a fixed
per-trade cost makes performance honest and nudges the rebalancer away from
low-value reallocations.

## What Changes

- Charge a fixed transaction cost on **every executed (recorded) trade**, buy or
  sell, applied at the single `record_trade` choke point so no caller can miss
  it. The amount is a tunable setting `TRANSACTION_COST_USD` (default `1.0`).
- Track cumulative fees in a **new non-nullable `total_fees` column** on
  `paper_trading_sessions`. Existing sessions backfill to `0.0` — fees are
  **forward-looking only**, no retroactive re-pricing of historical trades.
- Net fees into valuation: `total_value = allocated_capital + total_pnl −
  total_fees + unrealized`. This flows automatically into cash value, end-of-day
  value snapshots, and total-return %. Per-`ClosedPosition.realized_pnl` stays
  **gross** (fees are tracked separately, not folded into position PnL).
- Surface `total_fees` as a new field on the live session KPIs
  (`SessionKpis` → `PaperTradingSessionKpisRead`) and as a new KPI tile on the
  session detail page.
- Add rebalance-prompt **version 2** via an Alembic `bulk_insert` migration whose
  instructions statically describe the ~$1 per-executed-trade cost, so the agent
  weighs it before making small reallocations. Per the existing freeze design,
  only sessions built after this becomes the active version freeze v2; existing
  active sessions keep their frozen v1 but still incur real fees.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `ai-paper-trading`:
  - "Record sessions, trades, runs, and closed positions" — recording a trade now
    also charges `TRANSACTION_COST_USD` into the session's `total_fees`.
  - "Live session performance KPIs" — valuation subtracts `total_fees`; KPIs
    expose a new `total_fees` field.
  - "Versioned rebalancing prompt stored in the database" — a new version 2
    describes the per-trade cost so the agent avoids low-value churn; new sessions
    freeze v2 at build.
- `app-shell`:
  - "Session performance KPI tiles" — add a transaction-fees tile to the session
    KPI row.

## Impact

- **Backend**: `config.py` (`TRANSACTION_COST_USD`); `paper_trading/models.py`
  (`total_fees` column); `paper_trading/service.py` (`record_trade` charges the
  fee, `compute_session_value` net formula, `session_kpis` new field);
  `api/schemas.py` (`PaperTradingSessionKpisRead.total_fees`); new Alembic
  migration (add `total_fees` + backfill `0.0`; seed `rebalance_prompt` v2). Head
  advances from `c3f6a9d1e0b4`.
- **Frontend**: `types/api.ts` (`PaperTradingSessionKpis.total_fees`);
  `PaperTradingSessionPage` KPI row (new fees tile).
- **Behavior**: session portfolio values / total-return % for sessions that trade
  after this ships will be slightly lower (by accrued fees); realized-PnL per
  closed position is unchanged. No API breaking changes (additive field).
