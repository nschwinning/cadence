## 1. Executor: rebalance base capital becomes a per-run input (D2)

- [x] 1.1 Make `execute_rebalance` size against a per-run base capital rather than the executor's stored `allocated_capital` (accept a `base_capital` argument, or otherwise parametrise the rebalance base), leaving `execute_build` sizing off `allocated_capital` and `execute_close` untouched; verify `uv run mypy src/cadence` passes and existing executor tests still compile.
- [x] 1.2 Add/extend an executor unit test asserting that, for the same target weights and current positions, a larger rebalance base produces larger target position values (and thus buys toward them), while the build path is unchanged.

## 2. Rebalance seam: feed the session's current value (D1, D3)

- [x] 2.1 At the rebalance seam in `ai_portfolio/service.py` (~855), compute the session's current value via `paper_trading.service.compute_session_value(session, session_id=session_id, broker=broker).total_value` and use it as the rebalance base capital instead of `session_row.allocated_capital`; verify a service test that a session with a simulated gain sizes its rebalance targets against the grown value (gains redeployed, less idle cash).
- [x] 2.2 Add a service test that a session with a simulated loss sizes its rebalance targets against the reduced value rather than the original allocated capital.
- [x] 2.3 Confirm the build path still sizes against allocated capital; verify an existing or new build test asserts build target values are derived from the allocated capital (unchanged behavior).

## 3. Verification

- [x] 3.1 Backend: `uv run ruff check . && uv run mypy src/cadence && uv run pytest` all green.
- [x] 3.2 `openspec validate size-rebalance-on-live-value --strict` passes.
