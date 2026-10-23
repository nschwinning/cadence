## 1. Backend — build no longer allocates inline

- [x] 1.1 In `ai_portfolio/flows/build.py::run_build_event`, remove the inline opening-allocation block (the `create_rebalance_event` call, the `session_metadata["initial_rebalance_event_id"]` write, and the direct `run_rebalance_event(...)` call), leaving the shell portfolio + enrolled session creation and the order-less build-event finish intact; verify `session_metadata` no longer contains `initial_rebalance_event_id` after a build.
- [x] 1.2 Remove or update any now-unused imports/helpers in `build.py` left dangling by 1.1 (e.g. `create_rebalance_event` / `run_rebalance_event` if no longer referenced there); verify `uv run ruff check .` and `uv run mypy src/cadence` pass.
- [x] 1.3 Update the build-flow comments to describe the new behavior (build creates an enrolled empty session; opening allocation is produced by the first scheduled daily rebalance); verify the comments no longer reference an inline initial rebalance.

## 2. Backend — readiness gate intent + regression coverage

- [x] 2.1 Update `ai_portfolio/events.py::build_orders_settled` docstring/comments so they describe the three session generations accurately (new-flow sessions record no `initial_rebalance_event_id` and are ready because the fallback build event has zero orders); make no behavioral change to the resolution/reconcile/trade-count logic. Verify by reading the updated docstring against design D2.
- [x] 2.2 Add a test asserting a new-flow session (metadata has `build_event_id` but no `initial_rebalance_event_id`, and the build event recorded no trades) is reported **ready** by `build_orders_settled`; verify the test passes.
- [x] 2.3 Add/confirm regression tests that an ancient session (unsettled orders recorded under `build_event_id`) and a recent session (unsettled orders under `initial_rebalance_event_id`) are both reported **not ready**; verify the tests pass.

## 3. Backend — build produces an empty, enrolled session

- [x] 3.1 Update the build-flow tests so a completed build asserts: session status ACTIVE, `schedule_mode == DAILY_REBALANCING`, no open positions / no trades recorded, 100% cash equal to allocated capital, and no `initial_rebalance_event_id` in metadata; verify the tests pass.
- [x] 3.2 Remove or rewrite any existing build-flow test that asserted the inline initial rebalance placed opening trades at build time; verify the suite reflects the new no-inline-allocation behavior.

## 4. Backend — first scheduled rebalance allocates the empty session

- [x] 4.1 Add a test driving the first `rebalance_daily` run against a freshly built empty session and asserting it produces the opening allocation (sizes against current value = allocated capital, no sells, records trades + a run entry); verify the test passes.
- [x] 4.2 Add a test that a freshly built crypto-scope empty session is allocated by the weekend `rebalance_crypto_daily` run; verify the test passes.
- [x] 4.3 Add a test that a freshly built all-equity empty session whose first scheduled run falls while the equities market is closed records a skipped run with no orders and is allocated on a later run; verify the test passes.
- [x] 4.4 In `ai_portfolio/flows/rebalance.py`, let the weekend crypto-only run open the crypto sleeve of a freshly built **empty shell** (no positions, no portfolio picks) whose configured scope admits crypto, instead of skipping it for "holds no crypto to rebalance". Scope the change narrowly to the never-allocated empty shell so established sessions' weekend behavior is unchanged and the "no free cash to buy crypto" guard still applies; verify the crypto-opening test passes and the existing crypto-only skip tests still pass. (Required to satisfy the spec scenario "Crypto session allocated on the weekend cadence", which the empty-shell `any_crypto` gate would otherwise defeat.)

## 5. Frontend — honest build-completion copy

- [x] 5.1 Update `pages/portfolios/BuildAIPortfolioCard.tsx` so a successful build communicates that the portfolio was created and enrolled and will be allocated on its next daily rebalance, and renders no "added N assets" / opening-trades summary; verify in the UI copy.
- [x] 5.2 Update the `BuildAIPortfolioCard` Vitest test to assert the new completion copy and the absence of any opening-trades summary; verify `npm run test` passes for that file.

## 6. Verification gates

- [x] 6.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` all green.
- [x] 6.2 Frontend: `cd frontend && npm run typecheck && npm run test && npm run build` all green.
- [x] 6.3 `openspec validate defer-initial-allocation-to-daily-rebalance --strict` passes.
