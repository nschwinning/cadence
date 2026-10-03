## Context

See `proposal.md` — Why. Current state of the relevant seams (verified against the code):

- **`AIPortfolioExecutor.execute_rebalance`** (`ai_portfolio/executor.py`) builds `tickers = sorted(set(current_positions) | set(target_weight))` and loops once. Per ticker it calls `_rebalance_equity` / `_rebalance_crypto`, which **decide the side (by the sign of the delta), size the order, submit it via `broker.buy` / `broker.sell`, and build the `TradeResult` — all in one call.** Sells and buys are therefore interleaved in alphabetical ticker order. Each per-ticker body is wrapped in `try/except` so one failure records a not-executed `TradeResult` and the run continues. `base_capital` (the live session value) is never decremented as orders execute, and there is no per-order cash check in the executor.
- **Broker contract already carries fill state.** `broker.buy` / `broker.sell` return an `Order` with `order_id`, `status` (`OrderStatus`), and `filled_price`. `Order.is_complete` is true for `FILLED | CANCELLED | REJECTED`. `broker.get_order(order_id) -> Order | None` re-reads live status. `TradeResult` already carries `order_id` / `order_status` / `filled_price`.
- **Two fill models.** The `StubBroker` fills synchronously inside `buy`/`sell` (mutates cash/positions, returns `FILLED`; raises `OrderError` when cost > cash). The `AlpacaBroker` is asynchronous: `buy`/`sell` return `SUBMITTED`/`PENDING` with `filled_price=None`, and the true fill is only observable later via `broker.get_order` (the same path `paper_service.reconcile_session_orders` uses).
- **House idiom for fill gating.** The archived `defer-rebalance-until-build-orders-filled` change gates an action on real broker order status, treats "nothing to wait on ⇒ ready," and treats terminal-but-rejected as settled so a session is never stranded. This design applies the same shape inside a single run, between the sell phase and the buy phase.
- **Call site.** `run_rebalance_event` (`ai_portfolio/service.py`) calls `execute_rebalance(...)` once and passes the returned `list[TradeResult]` to `_apply_rebalance_trades`, which records each trade (executed or not) under the event. Preserving the `execute_rebalance(...) -> list[TradeResult]` signature keeps this call site unchanged.

## Goals / Non-Goals

**Goals:**
- Split order *decision/sizing* from order *submission* so the executor can emit all sells, confirm their fills, then emit all buys — without changing the delta/sign/sizing math or the `TradeResult` shape.
- Gate the buy phase on **real broker fill status** via `broker.get_order`, bounded by a configurable timeout, fail-safe toward not buying.
- Keep the stub (synchronous-fill) path and every existing rebalance test behaviour-identical: sells settle instantly, buys proceed in the same run.

**Non-Goals:**
- No new persisted state, DB column, migration, or cross-cron-tick phase machine — the queue and fill tracking are in-memory for the duration of one `execute_rebalance` call.
- No change to the daily-rebalance *trigger selection* (which sessions run), to build/close execution, to the stop-loss scan, or to guardrail math.
- Not fixing class-share Alpaca symbol routing or adding a per-order cash check beyond what the sell→buy ordering implies (out of scope).
- No per-buy sequencing: buys fire as one batch after sells settle (explicit user decision).

## Decisions

**1. Separate "plan" from "submit" inside `execute_rebalance`.**
Refactor `_rebalance_equity` / `_rebalance_crypto` so their delta/sign/sizing logic yields a **planned order intent** (ticker, class, side, quantity, reference price) instead of submitting inline. `execute_rebalance` then: (a) builds the full intent list over `sorted(set(current_positions) | set(target_weight))`, applying the existing market-closed-equity skip, crypto-only scope, below-min-notional / sub-one-share skips, and guardrail-clamped weights exactly as today; (b) partitions intents into **sells** and **buys**; (c) submits sells, (d) waits for them to settle, (e) submits buys (or withholds them on timeout). The submit step reuses the existing `broker.buy` / `broker.sell` calls and builds the same `TradeResult`.
- *Why over "just reorder the loop":* simply sorting sells-first within the current one-shot loop would order the *submissions* but, on the async Alpaca broker, buys would still be submitted before the sells actually fill — the exact failure we are fixing. The fill gate between phases is the point, and it needs the submit step isolated from the decision step.
- *Alternative considered — a persisted phase column driving two cron runs:* rejected by the user ("without persisting state"); also heavier (migration + trigger wiring) than the in-memory two-phase run, which already works for both broker models.

**2. Gate the buy phase on `broker.get_order`, poll-with-timeout, in memory.**
After submitting sells, collect their `order_id`s and poll `broker.get_order(order_id)` until every sell `is_complete` (filled/cancelled/rejected) or a configured timeout elapses. A sell that returns no `order_id` (nothing actually submitted) or is already terminal contributes nothing to wait on. On the stub, every sell is `FILLED` on return so the first check passes immediately with no real waiting.
- *Why poll `get_order` directly rather than call `reconcile_session_orders`:* `reconcile_session_orders` is DB-oriented (re-reads persisted `PaperTrade` rows and repairs ledger cost basis), but at executor time the sells have not been persisted yet — `_apply_rebalance_trades` records them only after `execute_rebalance` returns. Polling the broker by `order_id` is the same underlying signal without a persistence dependency, and keeps the executor free of DB access (consistent with its current design).
- *Why "terminal, not strictly filled":* mirrors the house idiom — a rejected/cancelled sell must not hang the run; the freed cash simply isn't there, and the dependent buys are sized against whatever actually freed up on the next run.

**3. Fill-wait timeout is fail-safe: withhold buys, keep sells.**
If the timeout elapses with sells still non-terminal, the executor does **not** submit the buys. It appends a not-executed `TradeResult` for each planned buy (`executed=False`, reason "sells not yet filled") so the outcome is observable in the run details, and returns. The sells that were submitted stay as-is; the next scheduled rebalance re-derives deltas from the (updated) ledger once the sells have reconciled.
- *Default timeout:* a new `settings` value (e.g. `REBALANCE_SELL_FILL_TIMEOUT_SECONDS`) with a modest default and a small poll interval. Under `ALPACA_STUB` the first poll already sees terminal sells, so the timeout path is never exercised offline/in tests.
- *Why withhold rather than buy anyway:* buying before the cash is confirmed is the original bug; on timeout the safe action is to not over-commit cash.

**4. Bounded retry of rejected orders, in memory.**
When a submit returns a terminal `REJECTED` (or raises the broker's order error), retry that single order up to a small configured max-attempts within the run before recording it not-executed. Applies to both phases. Keeps the existing "one failure never aborts the whole run" guarantee.
- *Default attempts:* a new `settings` value (e.g. `REBALANCE_ORDER_MAX_ATTEMPTS`) with a small default (e.g. 2–3). On the stub, an insufficient-funds sell/buy raises deterministically, so retry count is bounded and test-stable.

**5. Preserve signature and `TradeResult` semantics.**
`execute_rebalance(...)` keeps returning `list[TradeResult]` covering every planned order (executed sells, executed buys, skipped equities while closed, below-notional skips, withheld buys on timeout, retry-exhausted rejects). `run_rebalance_event` / `_apply_rebalance_trades` are unchanged; the `all(tr.executed ...)` → `SUCCEEDED`/`PARTIAL` event-status logic naturally reports a timeout-withheld run as `PARTIAL`.

## Risks / Trade-offs

- **Polling blocks the rebalance background worker for up to the timeout** → Mitigation: the rebalance already runs as a per-session background task; the timeout is bounded and the poll interval small, and the stub (tests) never waits. Choose a default timeout short enough not to stall the worker pool yet long enough for a normal market-hours fill.
- **A sell that fills *partially* then stalls** → `PARTIALLY_FILLED` is not terminal, so it would wait out the timeout and withhold buys (fail-safe). Accepted: partial fills are rare for the paper market orders used here, and withholding is the safe outcome; the next run redeploys whatever freed.
- **Buys sized against `base_capital` (live value), not against literal freed cash** → unchanged from today: sizing math is untouched; the sells-first ordering only ensures the cash is *real* before buys are placed, which is what prevents the rejection. A buy could still be trimmed by the broker if a sell was rejected, but the retry + next-run redeploy cover that.
- **Timeout path leaves the portfolio half-rebalanced for one cycle** → Accepted and observable (withheld buys recorded not-executed, event `PARTIAL`); the next scheduled rebalance completes the rotation. This is strictly better than today's "buy rejected for insufficient funds" failure.
- **Two new settings** → both have safe defaults and are inert under the stub, so no test or offline behaviour changes.

## Migration Plan

No data migration. Behaviour is in-memory and derived at runtime; rollback is reverting the code. Two new `settings` values ship with defaults, so existing deployments need no env change. Existing rebalance tests continue to pass unchanged because the stub settles sells synchronously; new tests cover the async ordering, the timeout withholding, and the retry path (via a fake broker with controllable fill status).
