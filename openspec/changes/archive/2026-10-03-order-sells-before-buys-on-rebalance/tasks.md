## 1. Config

- [x] 1.1 Add `REBALANCE_SELL_FILL_TIMEOUT_SECONDS` (bounded fill-wait) and `REBALANCE_ORDER_MAX_ATTEMPTS` (bounded retry) to the pydantic `settings` singleton with safe defaults and a small poll interval; verify `uv run python -c "from cadence.config import settings; print(settings.REBALANCE_SELL_FILL_TIMEOUT_SECONDS, settings.REBALANCE_ORDER_MAX_ATTEMPTS)"` prints the defaults.

## 2. Split order decision from submission in the executor

- [x] 2.1 Refactor `_rebalance_equity` / `_rebalance_crypto` (`ai_portfolio/executor.py`) so the delta/sign/sizing logic returns a planned order intent (ticker, asset class, side, quantity, reference price) instead of calling `broker.buy`/`broker.sell` inline; keep the below-one-share / below-min-notional / no-op skips returning "no intent". Verify existing executor unit tests still compile and the sizing math is unchanged by a focused test asserting the planned quantity for a known equity and crypto delta.
- [x] 2.2 Add an internal submit helper that takes a planned intent, calls the existing `broker.buy`/`broker.sell`, and builds the same `TradeResult` (carrying `order_id`/`order_status`/`filled_price`); verify a unit test that a submitted intent yields a `TradeResult` matching today's fields.

## 3. Two-phase sells-before-buys with fill gate

- [x] 3.1 Rewrite `execute_rebalance` to build the full intent list over `sorted(set(current_positions) | set(target_weight))` (preserving crypto-only scope, market-closed equity skip, guardrail-clamped weights, and `base_capital` sizing), then partition intents into sells and buys. Verify a test asserts that, given a mix of sell and buy deltas, all sell orders are submitted on the broker before any buy order (e.g. via a recording fake broker that logs call order).
- [x] 3.2 Submit all sells, then poll `broker.get_order(order_id)` until every submitted sell is `is_complete` (filled/cancelled/rejected) or the configured timeout elapses; treat a sell with no `order_id` or already-terminal as nothing-to-wait-on. Verify a test with an async fake broker (sell stays non-terminal, then flips terminal) that buys are withheld until all sells are terminal, then submitted.
- [x] 3.3 After sells settle, submit all buys in one batch. Verify a test that with a synchronous (stub) broker the sells settle immediately and the buys are submitted in the same run with freed cash available.
- [x] 3.4 On fill-wait timeout, withhold the dependent buys and append a not-executed `TradeResult` (`executed=False`, reason "sells not yet filled") for each; leave executed sells in place. Verify a test with an async fake broker whose sells never settle: buys are not submitted, each planned buy is recorded not-executed with the "sells not yet filled" reason, and the sells remain executed.
- [x] 3.5 Add bounded in-memory retry: when a submit returns terminal `REJECTED` (or raises the broker order error), resubmit up to `REBALANCE_ORDER_MAX_ATTEMPTS` before recording the order not-executed; applies to both phases and preserves "one failure never aborts the run". Verify a test where a fake broker rejects an order N-1 times then fills: it is retried and ends executed; and a test where it always rejects: it ends not-executed after the cap.

## 4. Preserve the call-site contract and existing behavior

- [x] 4.1 Confirm `execute_rebalance(...)` still returns `list[TradeResult]` covering every planned order (executed sells/buys, market-closed equity skips, below-notional skips, timeout-withheld buys, retry-exhausted rejects) and that `run_rebalance_event` / `_apply_rebalance_trades` are unchanged. Verify the existing `test_ai_portfolio_executor.py` and `test_ai_portfolio_service.py` suites pass unchanged (stub path).
- [x] 4.2 Verify crypto-only scope, market-closed equity skip, guardrail clamp, and live-value sizing are untouched by running their existing targeted tests green.

## 5. Full verification

- [x] 5.1 Run `uv run ruff check . && uv run mypy src/cadence && uv run pytest` from `backend/` — all green, including the new ordering/timeout/retry tests.
- [x] 5.2 Run `openspec validate order-sells-before-buys-on-rebalance --strict` — passes.
