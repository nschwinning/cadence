## 1. Build flow: shell + inline initial rebalance

- [x] 1.1 In `ai_portfolio/flows/build.py::run_build_event`, remove the `agent.build()` call, the `executor.execute_build()` call, and the build-trade recording (`_record_trades` + the build run entry), keeping portfolio creation, `create_session` (all frozen opt-ins/prompt versions/benchmark/metadata), and setting `event.session_id`/`event.portfolio_id`; verify by inspection that no `execute_build`/`agent.build` reference remains in the flow.
- [x] 1.2 After committing the shell, create a rebalance event for the new session via `service.create_rebalance_event` and drive it **directly** with `run_rebalance_event(session, rebalance_event_id, agent, broker, provider)` (no notifier, no job-runner submit — avoids the single-worker deadlock, see design D2); record the rebalance event id on the session (`session_metadata["initial_rebalance_event_id"]`); finish the build event as succeeded (the shell + opening-allocation trigger). Verify with a build-flow test asserting a rebalance event is created and produced the opening trades, and the build event itself placed no trades.
- [x] 1.3 Preserve the existing build-time request validation (e.g. empty-universe rejection) and the discovered-asset/scope handling that must still occur; verify the "Queue a build" and "Empty universe rejected" behaviors with existing/updated tests.

## 2. Readiness gate follows the opening allocation

- [x] 2.1 Update `ai_portfolio/events.py::build_orders_settled` to read the initial rebalance event's trades from `session_metadata["initial_rebalance_event_id"]` when present, falling back to `build_event_id` for legacy sessions; verify with unit tests for (a) a new session whose initial-rebalance orders are unsettled → not ready, (b) same settled → ready, (c) a legacy session (only `build_event_id`) → unchanged behavior.
- [x] 2.2 Confirm the daily and crypto-daily cron targeting is unchanged and still calls the updated readiness gate; verify with a test that a freshly built daily session is deferred until its initial-rebalance orders settle, then triggered.

## 3. Opening-allocation behavior (reuse, no special-casing)

- [x] 3.1 Verify (via tests, no new code) that the initial rebalance for a fresh session sizes against current value = allocated capital with no sells and a buy-only run, exactly as `execute_rebalance` already handles an empty ledger.
- [x] 3.2 Verify (via tests) the opening allocation applies a rebalance-only enhancement end-to-end — e.g. a session with `use_fundamentals` (frozen ≥ version) has fundamentals attached on its initial rebalance, and a trend-opted session applies the trend gate at the opening allocation.
- [x] 3.3 Verify (via a test) that a manual (non-daily) session is allocated by the initial rebalance at creation (does not sit empty) while the market is open, and that a market-closed all-equity opening allocation records a skipped run with no orders.

## 4. Dead-code and test cleanup

- [x] 4.1 Remove/replace build-executor tests that asserted `execute_build` sizing with tests for the new build-flow behavior; mark `AIPortfolioExecutor.execute_build`, `AIPortfolioAgent.build`, and the build prompt as unreferenced dead code (leave in place for a follow-up, or delete if trivially safe) and verify nothing in `src/cadence` still imports/calls them (`grep`).

## 5. Verification gates

- [x] 5.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` all green.
- [x] 5.2 Frontend only if touched (no change expected): no frontend files were touched by this change, so the frontend gate is not applicable.
- [x] 5.3 `openspec validate route-initial-allocation-through-rebalance --strict` passes.
