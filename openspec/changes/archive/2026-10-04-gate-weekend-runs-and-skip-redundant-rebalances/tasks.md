## 1. Configured-scope helper

- [x] 1.1 Add `session_allows_crypto(session_row: PaperTradingSession) -> bool` to `ai_portfolio/service.py`: read `asset_types` from `session_row.session_metadata` (default `AssetScope.BOTH.value`) and return `AssetCategory.CRYPTO in scope_categories(asset_scope)`.
- [x] 1.2 Add unit tests: returns False for `stocks`, True for `crypto` and `both`, and True for a session with no persisted scope (defaults to both).

## 2. Weekend crypto rebalance selection by scope

- [x] 2.1 In `api/routers/ai_portfolio.py::rebalance_crypto_daily`, replace the `session_involves_crypto(db, session_row)` gate with `session_allows_crypto(session_row)`; bucket excluded sessions into the renamed `skipped_not_crypto_scope`.
- [x] 2.2 Rename the `skipped_no_crypto` field to `skipped_not_crypto_scope` on `AIDailyCryptoRebalanceResponse` (`api/schemas.py`) and its frontend TS mirror in `frontend/src/types/api.ts`.
- [x] 2.3 Update/extend API tests: a stocks-only-scoped session that holds crypto is reported under `skipped_not_crypto_scope` and not triggered; crypto- and both-scoped sessions are triggered.

## 3. Weekend P&L snapshot/notification gating

- [x] 3.1 In `ai_portfolio/service.py::snapshot_all_sessions`, compute `is_weekend = as_of.weekday() >= 5` from the `_SNAPSHOT_TZ`-derived `as_of`; in the per-session loop `continue` (record no snapshot, send no push) when `is_weekend and not session_allows_crypto(session_row)`.
- [x] 3.2 Add tests: on a weekend, a stocks-only session gets no snapshot and no notification while crypto/both sessions still snapshot + notify; on a weekday, all active AI sessions snapshot + notify (unchanged).

## 4. Skip buy-only rebalance with no deployable cash

- [x] 4.1 In `ai_portfolio/executor.py`, set `self.skipped_noop = False` in `__init__` and add `unallocated_cash: float | None = None` to `execute_rebalance`.
- [x] 4.2 After Phase 0 builds the intent lists and before Phase 1 submits, compute `reserve = base - net_base` and `deployable_cash = (unallocated_cash or 0.0) - reserve`; when `unallocated_cash is not None and not sell_intents and deployable_cash <= 0.0`, set `self.skipped_noop = True` and return the `skips` list without submitting any order.
- [x] 4.3 In `ai_portfolio/service.py::run_rebalance_event`, pass `unallocated_cash=valuation.cash_value` to `execute_rebalance`; immediately after, when `executor.skipped_noop`, record a SKIPPED run (reusing the existing `nothing_tradable` recording + `_finish_event(..., EventStatus.SKIPPED)` path), send the informational skip notification (Task 6, buy-only reason) rather than a trade-success notification, and return before `_apply_rebalance_trades`.
- [x] 4.4 Add executor tests: buy-only plan + no deployable cash sets `skipped_noop` and submits nothing; buy-only plan + deployable cash submits the buys (not skipped); a plan with ≥1 sell runs regardless of cash; `unallocated_cash=None` preserves current behavior.
- [x] 4.5 Add service tests: a rebalance that resolves to buy-only with no deployable cash (including the first rebalance right after a build) records a SKIPPED run and sends no rebalance notification; a buy-only run with deployable cash and a run with sells still execute and notify.

## 5. Pre-agent skip for a crypto-only run with nothing to act on

- [x] 5.1 In `ai_portfolio/service.py::run_rebalance_event`, extend the crypto-only `nothing_tradable` determination to also skip (before invoking the agent) when `not has_crypto_positions and deployable_cash <= 0.0`, where `has_crypto_positions = any(asset_classes.get(t) == AssetClass.CRYPTO for t in positions)`, `reserve = max(crypto_budget * settings.REBALANCE_CASH_BUFFER_PCT, settings.TRANSACTION_COST_USD)`, and `deployable_cash = valuation.cash_value - reserve`; record a SKIPPED run via the existing path and send the informational skip notification (Task 6, crypto-only reason).
- [x] 5.2 Add service tests: a crypto-scoped session holding only equities with no free cash skips the crypto-only run before the agent runs (no agent invocation, no orders, equities untouched); the same session with deployable cash and crypto targets proceeds; a session holding crypto proceeds.

## 6. Informational skip notification for engaged-but-skipped runs

- [x] 6.1 In `ai_portfolio/service.py`, add a helper `_notify_rebalance_skipped(notifier, portfolio_name, reason, *, crypto_only)` that sends one informational Pushover via `_notify_safely` (title e.g. `Cadence: {portfolio} rebalance skipped`, body carrying the human-readable `reason`); it SHALL be a no-op when `notifier is None`.
- [x] 6.2 Call `_notify_rebalance_skipped` from the pre-agent crypto-only skip path (Task 5, reason "holds no crypto and no free cash to buy crypto") and from the post-plan `skipped_noop` path (Task 4.3, reason "already deployed — buy-only with no free cash"); resolve the session's portfolio name the same way the trade-success notification does. Leave the scope-excluded path in `rebalance_crypto_daily` (Task 2) and the weekend stocks-only snapshot skip (Task 3) silent — no notification.
- [x] 6.3 Add service tests: an engaged crypto-only skip and an engaged buy-only skip each send exactly one informational notification naming the portfolio + reason (and not a trade-success notification); a scope-excluded weekend session and a weekend stocks-only snapshot-skipped session send no notification.

## 7. Verify

- [x] 7.1 From `backend/`: `uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 7.2 From `frontend/`: `npm run typecheck && npx vitest run && npm run build` (covers the renamed response field).
- [x] 7.3 `openspec validate gate-weekend-runs-and-skip-redundant-rebalances --strict`.
