## Context

See proposal.md — Why. Relevant current state (verified against the code):

- Session asset scope lives only in `paper_trading_sessions.session_metadata` JSONB under `asset_types` (default `AssetScope.BOTH.value`). `scope_categories(scope)` (`assets/category.py:59`) maps a scope string → `frozenset[AssetCategory]`; `AssetScope.STOCKS → {STOCK}`, `CRYPTO → {CRYPTO}`, `BOTH → {STOCK, CRYPTO}`.
- `api/routers/ai_portfolio.py::rebalance_crypto_daily` (the weekend crypto cron) selects active `DAILY_REBALANCING` AI sessions, then skips a session via `ai_service.session_involves_crypto(db, session_row)` (a **holdings** check: open positions / portfolio targets), bucketing it as `skipped_no_crypto`.
- `ai_portfolio/service.py::snapshot_all_sessions(session, *, broker, notifier, as_of=None)` snapshots **and** sends one P&L push **per** active AI session, with no weekend or scope gate. `as_of` defaults to `datetime.now(tz=_SNAPSHOT_TZ).date()`; `_SNAPSHOT_TZ = ZoneInfo("America/New_York")`.
- `ai_portfolio/service.py::run_rebalance_event` already has a pre-agent `nothing_tradable` skip (crypto-only with no crypto, or market-closed with no crypto) that records a SKIPPED run via `paper_service.record_session_run` + `_finish_event(..., EventStatus.SKIPPED)` and returns. It computes `valuation = compute_session_value(...)` whose `valuation.cash_value` **is** the session's unallocated/free cash, and passes `base_capital = crypto_budget if crypto_only else valuation.total_value` to the executor. The rebalance Pushover push fires only when `notifier is not None and executed > 0`.
- `AIPortfolioExecutor.execute_rebalance` is two-phase: Phase 0 plans `sell_intents` / `buy_intents` / `skips` (`_OrderIntent`) for all tickers **before** any submission (executor.py ~485–551); Phase 1 submits sells; Phase 2 gates buys on sell fills. `net_base = self._reserve_cash_buffer(base, len(tickers))` (executor.py:483) shrinks the sizing base by the reserved cash buffer. The executor does not read live cash; it only knows `base`/`net_base`.
- `_trading_days_ahead` (service.py:1306) already approximates trading days with `moment.weekday() < 5`, establishing the calendar weekday/weekend convention (no exchange-holiday calendar).

## Goals / Non-Goals

**Goals:**
- Configured scope (not holdings) decides weekend crypto rebalance selection and weekend P&L snapshot/notification.
- Skip any rebalance run whose plan is buy-only with no deployable unallocated cash, decided from the planned intents before submitting.
- No migration; no frontend behavior change beyond the renamed cron skip bucket.

**Non-Goals:**
- Changing weekday rebalance selection or weekday snapshot behavior.
- Changing the per-run `nothing_tradable` pre-agent skip or the crypto-only universe restriction.
- Reworking sizing math or the cash buffer itself (`reserve-rebalance-cash-buffer` owns that).
- Skipping the agent call for the buy-only case (the plan is only known after the agent proposes targets; see Risks).

## Decisions

### 1. `session_allows_crypto(session_row) -> bool` as the scope gate
New public helper in `ai_portfolio/service.py`: read `asset_types` from `session_row.session_metadata` (default `AssetScope.BOTH.value`) and return `AssetCategory.CRYPTO in scope_categories(asset_scope)`. It needs no DB access (unlike `session_involves_crypto`, which stays as-is for any other caller). Chosen over extending `session_involves_crypto` because the two now answer different questions (configured vs held).

### 2. Weekend crypto rebalance selection (`rebalance_crypto_daily`)
Replace the per-session `if not ai_service.session_involves_crypto(db, session_row)` gate with `if not ai_service.session_allows_crypto(session_row)`. Rename the response bucket `skipped_no_crypto` → `skipped_not_crypto_scope` (field on `AIDailyCryptoRebalanceResponse` + the TS mirror) to reflect the new meaning. This endpoint is cron-only (not surfaced in the UI), so the rename is low-risk.

### 3. Weekend P&L gating (`snapshot_all_sessions`)
Compute `is_weekend = as_of.weekday() >= 5` (Sat=5, Sun=6) once, using the existing `_SNAPSHOT_TZ`-derived `as_of`. In the per-session loop, when `is_weekend and not session_allows_crypto(session_row)`, `continue` before recording the snapshot or sending the push. Weekday runs and crypto/both weekend sessions are unchanged. Returning only the sessions actually snapshotted keeps the "best/worst holding across snapshotted sessions" report correct.

### 4. Buy-only / no-deployable-cash skip in the executor
`execute_rebalance` gains `unallocated_cash: float | None = None`; `__init__` sets `self.skipped_noop = False`. After Phase 0 populates the intent lists and before Phase 1 submits:
- `reserve = base - net_base` (the buffer amount already reserved for sizing).
- `deployable_cash = (unallocated_cash or 0.0) - reserve`.
- If `unallocated_cash is not None and not sell_intents and deployable_cash <= 0.0`: set `self.skipped_noop = True` and return the `skips` list (so any market-closed / no-quote skips are still surfaced) without submitting anything.

Guarding on `unallocated_cash is not None` preserves current behavior for any caller that does not pass it (and all existing executor tests, which construct intents directly). Deciding in the executor honors "after the run has planned its intents"; the alternative (re-deriving buy/sell signs in the service) was rejected as duplicated sizing logic that could drift from the executor's rounding.

### 5. Service maps the executor skip to a SKIPPED run
`run_rebalance_event` passes `unallocated_cash=valuation.cash_value` to `execute_rebalance`. Immediately after the call, if `executor.skipped_noop`, record a SKIPPED run exactly like the existing `nothing_tradable` path (`record_session_run` with a skip detail + `_finish_event(..., EventStatus.SKIPPED)`), send no notification, and return before `_apply_rebalance_trades`. Because the push is already gated on `executed > 0`, no rebalance notification fires for the skipped run even independent of this branch.

### 6. Pre-agent skip for a crypto-only run with nothing to act on
Extend the existing crypto-only `nothing_tradable` determination in `run_rebalance_event` so it also short-circuits — before the agent runs — when the session holds no crypto and has no deployable cash to buy crypto. Concretely, keep the current `not any_crypto` disjunct and add a second one:
- `has_crypto_positions = any(asset_classes.get(t) == AssetClass.CRYPTO for t in positions)`.
- `reserve = max(crypto_budget * settings.REBALANCE_CASH_BUFFER_PCT, settings.TRANSACTION_COST_USD)` (candidate count is unknown pre-agent; one fee is a safe floor).
- `deployable_cash = valuation.cash_value - reserve`.
- `nothing_tradable (crypto_only) = (not any_crypto) or (not has_crypto_positions and deployable_cash <= 0.0)`.

This catches the common weekend case of a both-scoped session holding only equity shares with no free cash (the new user-reported case) without paying for an agent call. The existing post-plan `skipped_noop` (Decision 4/5) remains the safety net for full runs and for anything that slips past this pre-agent check. Truth table with no crypto positions: no crypto targets → skip (unchanged); targets crypto + no cash → skip (new); targets crypto + cash → run (deploys cash); holds crypto → always run (agent may trim/rotate).

### 7. Informational skip notification
When `run_rebalance_event` records a SKIPPED run for a session it actually engaged — both the pre-agent crypto-only path (Decision 6) and the post-plan `skipped_noop` path (Decision 5) — it SHALL send one informational Pushover via `_notify_safely` (title e.g. `Cadence: {portfolio} rebalance skipped`, body carrying the human-readable skip reason). A small helper `_notify_rebalance_skipped(notifier, portfolio_name, reason, *, crypto_only)` centralizes the message so both paths share it. The reason strings: crypto-only no-crypto/no-cash → "holds no crypto and no free cash to buy crypto"; full market-closed/no-crypto (existing `nothing_tradable`) → "market closed with nothing to trade"; post-plan buy-only → "already deployed — buy-only with no free cash". Guiding principle (user): inform only when the run engaged the session. Therefore the **silent** cases send nothing: a session excluded from the weekend crypto batch for not being crypto-scoped (handled in the router before any per-session run) and a stocks-only session skipped on a weekend snapshot (`snapshot_all_sessions` `continue`). The push is still never the trade-success push (that stays gated on `executed > 0`).

### 8. Weekend determination
Saturday/Sunday by calendar in `_SNAPSHOT_TZ` (`weekday() >= 5`), ignoring exchange holidays — consistent with `_trading_days_ahead`. The weekend crypto rebalance "weekend-ness" is a deployment concern (which cron fires `rebalance_crypto_daily`); its selection rule (Decision 2) applies whenever it runs, so it needs no in-code weekend check.

## Risks / Trade-offs

- [The agent still runs for a buy-only/no-cash rebalance before the skip is detected, costing one agent call] → Acceptable: the expensive, user-visible costs are transaction fees and Pushover noise, both avoided. The plan (buy vs sell) is only knowable after the agent proposes targets, so a pre-agent skip is not possible without duplicating sizing.
- ["First run after build always skipped" depends on the agent returning a buy-only plan] → Right after a build, positions sit at target with only the reserved buffer as cash, so any proposed plan is buy-only with no deployable cash and is skipped. If the agent proposes a genuine reallocation (sells), the run proceeds — which is the correct behavior per the general rule.
- [`deployable_cash` uses `reserve = base - net_base`, a total-value-based reserve subtracted from cash] → For a freshly built session `cash ≈ reserve`, so `deployable_cash ≈ 0` and it skips as intended; when real free cash exists it is positive and the run proceeds. Edge cases near zero only affect whether a marginal buy-only run is skipped, never cash-negativity (the buffer still protects that).
- [Renaming `skipped_no_crypto` → `skipped_not_crypto_scope` is an API field change] → The endpoint is cron-only; update the Pydantic schema, the TS mirror, and tests together.
- [`session_involves_crypto` may become unused] → Leave it in place; it is a harmless public helper and may be used by tests/future callers.

## Migration Plan

No DB migration (scope already in `session_metadata`). Pure logic + settings-free. Rollback is reverting the code; no data to undo. Deployment cadence (which days `rebalance_crypto_daily` / `snapshot-daily` fire) is unchanged and remains a cron concern.
