## 1. Readiness signal (service)

- [x] 1.1 Add a helper (e.g. `list_build_trades(db, session)` or resolve via `session_metadata["build_event_id"]` → the build event's `PaperTrade` rows) that returns a session's initial build orders; verify a unit test returns exactly the build event's trades and an empty list for a session with no build event. — Resolved inline in `build_orders_settled` via `session_metadata["build_event_id"]` + existing `paper_service.get_trades_by_event`.
- [x] 1.2 Add `session_build_orders_settled(db, session, broker) -> bool` in `paper_trading/service.py` (or an `ai_portfolio/service.py` wrapper) that reconciles the session's non-terminal build orders via the existing `reconcile_session_orders`, then returns True iff every build order with an `order_id` is in a terminal state (filled, or cancelled/rejected) and False while any is still non-terminal; verify unit tests cover: all filled → True, one still SUBMITTED/PENDING → False, no build orders → True, mixed filled + cancelled/rejected → True. — Added `ai_service.build_orders_settled(db, broker, session_row)`.
- [x] 1.3 Make the helper fail safe: when the broker reconcile raises/cannot confirm status, treat the session as not ready (return False) rather than assuming filled; verify a test with a broker stub that raises returns False.

## 2. Trigger gate (router)

- [x] 2.1 In `rebalance_daily` (`api/routers/ai_portfolio.py`), after the existing active + AI + `DAILY_REBALANCING` filter and the in-flight check, call the readiness helper per candidate and move not-ready sessions into the skipped set instead of starting a rebalance; verify a test where a session with unfilled build orders is not started and appears in the skipped ids.
- [x] 2.2 Report a build-order-deferred session as skipped distinctly from an already-running skip (a reason tag if the response carries reasons, otherwise ensure it is included among skipped ids); verify the trigger response test asserts the deferred session id is present in skipped and the ready session id is present in triggered. — Added `skipped_awaiting_build_fill` to `AIDailyRebalanceResponse`.
- [x] 2.3 Confirm the manual single-session rebalance path is unchanged (no readiness gate applied); verify an existing/added test that a manual rebalance on a session with unfilled build orders still proceeds. — Manual `start_rebalance` path does not call the gate.

## 3. Integration & regression

- [x] 3.1 Add an integration test: build a session against a broker whose orders stay SUBMITTED, call the daily rebalance trigger, assert the session is skipped (deferred); then flip the orders to FILLED, reconcile, call the trigger again, assert the session is now triggered. — `test_rebalance_daily_includes_session_once_build_orders_fill` (+ `_defers_...`, `_manual_..._not_deferred`).
- [x] 3.2 Confirm existing daily-rebalance tests still pass under the immediate-fill stub broker (sessions ready right away); verify the full backend suite is green with `uv run pytest` (and `uv run ruff check .` / `uv run mypy src/cadence` clean).
