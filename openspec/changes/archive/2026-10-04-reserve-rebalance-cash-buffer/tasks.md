## 1. Settings

- [x] 1.1 Add `REBALANCE_CASH_BUFFER_PCT: float = 0.015` to `backend/src/cadence/config.py` near the other `REBALANCE_*` settings, with a comment explaining it reserves a cash buffer (greater of this fraction of the sizing base and the estimated run fees) so builds/rebalances do not drive unallocated cash negative.

## 2. Executor cash-buffer reserve

- [x] 2.1 Add a pure helper on `AIPortfolioExecutor` (e.g. `_reserve_cash_buffer(base: float, candidate_count: int) -> float`) that returns `max(base - max(base * settings.REBALANCE_CASH_BUFFER_PCT, candidate_count * settings.TRANSACTION_COST_USD), 0.0)`.
- [x] 2.2 In `execute_build`, compute `net_base` from `self.allocated_capital` with `candidate_count = len(stocks)` and size every `_open_long` against `net_base * weight` (both the `caps is None` and guardrail branches), replacing `self.allocated_capital * ...`.
- [x] 2.3 In `execute_rebalance`, after guardrail clamping and before the Phase-0 sizing loop, compute `net_base = self._reserve_cash_buffer(base, len(tickers))` and pass `net_base` into `_plan_equity`/`_plan_crypto` in place of `base`. Leave crypto-only scoping, `market_open` skip, and sells-before-buys phasing untouched (the crypto budget already flows through `base`).
- [x] 2.4 Confirm `settings` is imported in `executor.py` (it is already used for `REBALANCE_SELL_FILL_*`).

## 3. Tests (`backend/tests/test_ai_portfolio_executor.py`)

- [x] 3.1 Rebalance: a fully-invested target (weights sum ~1.0) against a session whose value includes gains leaves unallocated cash ≥ 0 after fees (assert via resulting positions cost basis vs base, or via the StubBroker cash). 
- [x] 3.2 Buffer is `max(pct, fee estimate)`: construct one case where the fee estimate dominates (many tickers, small base) and one where the percentage dominates (few tickers, large base); assert the net base used for sizing matches the greater reserve.
- [x] 3.3 Build reserves the buffer: `execute_build` deploys against `allocated_capital` minus the reserve (assert bought notional ≤ `allocated_capital - reserve`).
- [x] 3.4 Zero disables: with `REBALANCE_CASH_BUFFER_PCT = 0` and `TRANSACTION_COST_USD = 0` (monkeypatch settings), sizing matches the pre-change quantities.
- [x] 3.5 Unchanged behavior: crypto-only scoping, `market_open=False` equity-skip, and guardrail clamp still produce the same order set/sides as before (buffer only shrinks quantities).
- [x] 3.6 Audit existing build/rebalance qty assertions in the suite and update expected shares/quantities for the default buffer, or pin the buffer to 0 in fixtures that assert no-buffer sizing.

## 4. Verify

- [x] 4.1 From `backend/`: `uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 4.2 `openspec validate reserve-rebalance-cash-buffer --strict`.
