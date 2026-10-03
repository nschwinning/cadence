## Why

The AI rebalance executor processes tickers alphabetically, interleaving sells and buys in a single pass. Because buys can therefore be submitted before the sells that fund them have freed up cash, a rebalance that rotates capital out of one holding into another can hit "insufficient buying power" rejections on the live Alpaca broker (where fills are asynchronous), leaving the portfolio in a half-rebalanced state. Trades should be ordered: sell first, confirm the cash is real, then buy.

## What Changes

- The AI rebalance SHALL submit **all sells before any buys**: it first places every sell/exit order, then places buys only after the sells have reached a terminal filled state at the broker.
- The sell→buy fill gate reuses the house idiom from the archived `defer-rebalance-until-build-orders-filled` change: readiness is keyed on **real broker order status** (polled via `broker.get_order`), "nothing to wait on ⇒ ready," and a terminal-but-rejected sell counts as settled (it never strands the run). Under the immediate-fill stub broker, sells settle instantly so buys proceed in the same run — existing offline/test behaviour is preserved.
- Buys are submitted **all at once** after the sells settle (not one order at a time).
- The fill wait is **bounded by a configurable timeout**. On timeout (e.g. sells placed while the market is closed never fill), the executor is **fail-safe**: it skips the dependent buys for this run and records them as not-executed with a "sells not yet filled" reason. The next scheduled rebalance re-derives the deltas from the (now partially-updated) ledger.
- Failed (rejected) sell or buy orders are **resubmitted** via a bounded in-memory retry within the same run.
- No new persisted state: the sell/buy queue and fill tracking live **in memory within the single rebalance run**. No new DB column, no migration, no cross-tick phase machine.
- Behaviour that is explicitly unchanged: the crypto-only weekend scope, the market-closed equity skip, the risk-guardrail weight clamp, live-value (`base_capital`) sizing, the `TradeResult` shape, and the `execute_rebalance(...) -> list[TradeResult]` signature (so `run_rebalance_event` / `_apply_rebalance_trades` need no structural change).

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `ai-paper-trading`: the requirement governing AI rebalance order execution gains a sells-before-buys ordering guarantee with a broker-fill gate between the two phases (all sells submitted and filled before any buy), batched buys, bounded fail-safe fill-wait timeout, and bounded retry of rejected orders — all in-memory, no new persistence.

## Impact

- **Backend — executor:** `ai_portfolio/executor.py` `execute_rebalance` (and its `_rebalance_equity` / `_rebalance_crypto` helpers) is restructured to separate order *decision/sizing* from order *submission*: classify every ticker into a sized sell-intent or buy-intent, submit sells, poll their fills via `broker.get_order` until terminal (bounded timeout), then submit buys. Retains the per-order try/except so one failure cannot abort the run.
- **Backend — config:** a new fill-wait timeout setting (and optionally a max-retry-attempts setting) on the pydantic `settings` singleton with sensible defaults; the stub broker resolves fills immediately so the timeout is never hit offline/in tests.
- **Broker I/O:** reuses the existing `Broker.get_order` and the already-returned `Order.order_id` / `Order.status` / `Order.filled_price` — no new broker Protocol method. StubBroker fills synchronously (buys-after-sells still succeed in-run); AlpacaBroker fills asynchronously (the poll observes the real terminal status).
- **No schema/migration, no API change, no frontend change.** The service call site (`run_rebalance_event` → `execute_rebalance` → `_apply_rebalance_trades`) keeps the same contract; `_apply_rebalance_trades` already records whatever `TradeResult` list it is given (including not-executed buys).
- **Unaffected:** build execution, close/liquidation, stop-loss scan, the daily-rebalance *trigger selection* (this change is executor-internal, not a trigger gate), guardrails, and the technical-indicator strategy.
