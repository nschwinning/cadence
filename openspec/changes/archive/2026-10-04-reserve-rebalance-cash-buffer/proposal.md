## Why

Paper-trading sessions now show **negative unallocated cash at times**. The AI
executor sizes buys against the session's live total value with the agent's
target weights summing to ~1.0 and reserves nothing for costs, so it deploys
effectively 100% of available cash into position cost basis. The per-trade
`TRANSACTION_COST_USD` fee (charged on top of each fill) and live-Alpaca
market-order fill slippage then push unallocated cash below zero. Free cash
should never go negative in a long-only, cash-funded session.

## What Changes

- The AI executor reserves a **cash buffer** before sizing orders, so buys can
  never claim 100% of the session's value. The reserve is the **greater of**:
  1. a configurable **percentage** of the sizing base, and
  2. the **estimated total fees** for the run (candidate trade count ×
     `TRANSACTION_COST_USD`).
- The reserve is applied **consistently at both build and rebalance** sizing:
  the base the executor sizes target positions against is reduced by the buffer
  before any per-ticker allocation is computed. Guardrail clamping, crypto-only
  scoping, `market_open` equity-skip, the sells-before-buys phasing, and the
  `base_capital` live-value sizing are all preserved — the buffer only shrinks
  the base they already operate on.
- New settings: a rebalance/build cash-buffer **percentage** (default ~1.5%).
  The per-trade fee input reuses the existing `TRANSACTION_COST_USD`.
- No schema change, no migration — settings + executor logic only.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `ai-paper-trading`: the AI executor SHALL reserve a cash buffer (the greater
  of a configured percentage of the sizing base and the estimated total trade
  fees for the run) before sizing build and rebalance orders, so a session's
  unallocated cash is not driven negative by fully deploying value plus fees and
  slippage.

## Impact

- **Code**: `ai_portfolio/executor.py` (`execute_build`, `execute_rebalance`,
  and the shared sizing base), `config.py` (new buffer-percentage setting).
- **Behavior**: builds and rebalances leave a small cash reserve; a fully
  invested target no longer overspends into negative free cash. No API or
  frontend surface change; KPIs/snapshots reflect the now non-negative cash.
- **Tests**: `backend/tests/test_ai_portfolio_executor.py` (sizing/cash
  assertions). No DB, migration, or cross-tick state.
