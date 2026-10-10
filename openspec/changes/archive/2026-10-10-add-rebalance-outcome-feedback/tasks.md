## 1. Per-session flag + window (model + migration + build params)

- [x] 1.1 Add `learning_feedback_enabled: Mapped[bool]` (non-nullable, `server_default` false) and `learning_feedback_window: Mapped[int | None]` (nullable, meaningful only when enabled) to `PaperTradingSession` in `paper_trading/models.py`, mirroring the `stop_loss_enabled`/`stop_loss_pct` pair with comments explaining they are frozen at build.
- [x] 1.2 Create an Alembic migration (`down_revision` = current head; confirm via `uv run alembic heads`) that adds the two session columns (`learning_feedback_enabled` with a `false` server default, backfilled to false; `learning_feedback_window` nullable) **and the `paper_trades.fee` column** (non-nullable, `0` server default, backfilled to 0 — see §4b) and whose `downgrade` drops all three. Verify round-trip (`upgrade head` then `downgrade -1`) and `alembic check` shows no drift.
- [x] 1.3 Add `learning_feedback_enabled: bool = False` and `learning_feedback_window: int | None = None` to `AIBuildParams` in `ai_portfolio/params.py` and thread both through `to_dict`/`from_payload` (mirroring the other opt-in knobs).
- [x] 1.4 Persist the flag and window onto the new session in `ai_portfolio/flows/build.py` at build time, defaulting the window to `LEARNING_FEEDBACK_DEFAULT_WINDOW` when the flag is on and no window was supplied.

## 2. Configuration

- [x] 2.1 Add `LEARNING_FEEDBACK_DEFAULT_WINDOW: int = 5` to the settings singleton in `config.py` (build-form default / fallback only), placed with the other `*_DEFAULT_*` build-knob settings.

## 3. API schema surface

- [x] 3.1 Add `learning_feedback_enabled: bool = False` and an optional `learning_feedback_window: int | None = None` to the AI build request schema in `api/schemas.py`; validate the window is positive when the flag is on (mirroring the guardrail/stop-loss validators) and pass both into `AIBuildParams` where the build request is translated.
- [x] 3.2 Add `learning_feedback_enabled: bool` and `learning_feedback_window: int | None` to the session read schema and ensure the router mapping populates them from the session row.

## 4. Snapshot read helper

- [x] 4.1 Add `list_daily_run_snapshots(session, session_id, limit)` to `paper_trading/service.py`, mirroring `get_daily_run_snapshot`: select the session's `session_daily_run_snapshots` rows ordered by `run_date DESC`, limited to `limit`; return the model rows. Read-only, no new column/index.
- [x] 4.2 Unit test the helper: returns most-recent-first, respects the limit when there are more rows than the window, and returns an empty list when the session has none.

## 4b. Persist per-trade fee for an exact cost-forward distillation (write-path)

- [x] 4b.1 Add a `fee: Mapped[float]` column to `PaperTrade` in `paper_trading/models.py` (non-nullable, `default=0.0`, `server_default="0"`) holding the transaction cost assessed when the trade was recorded. (Column added by the §1.2 migration.)
- [x] 4b.2 In `paper_trading/service.py::record_trade`, set `trade.fee` to the asset-class-aware fee it already computes (equities `0.0`; crypto `CRYPTO_FEE_PCT × notional`) before commit, so the single choke point records the per-trade fee alongside accumulating the session's cumulative `total_fees` (unchanged).
- [x] 4b.3 In `ai_portfolio/snapshots.py`, have `_order_document` include the order's `fee` and `_build_run_document` record the day's `fees_total` (sum of the day's order fees) in the learning document; a no-run day records `fees_total = 0`.
- [x] 4b.4 Tests: `record_trade` stores the crypto fee on the trade and `0.0` for an equity trade; `_build_run_document` carries per-order `fee` and the day's `fees_total`.

## 5. Prompt distillation (cost-forward)

- [x] 5.1 Add a pure helper (e.g. `_summarize_recent_outcomes`) beside `_build_rebalance_input` in `ai_portfolio/agent.py` that maps each snapshot `document` to one compact **cost-forward** per-day line — leading with net-of-fees realized P&L (gross `run.run_stats.realized_pnl` minus the day's `fees_total`), then fees paid (`fees_total`) and order/churn count, then end-of-day valuation, plus day return and notable gate/skip counts when present — reading defensively with `.get(...)` so missing/malformed documents contribute no line (a missing `fees_total` reads as 0, so net equals gross); return `None`/empty for an empty input.
- [x] 5.2 Extend `_build_rebalance_input` with an optional `recent_outcomes` parameter (default empty) that renders an advisory "Recent run outcomes" section only when the distillation is non-empty, keeping the prompt byte-identical otherwise. Preserve determinism and the existing tool-less structured-output contract.
- [x] 5.3 Unit tests: distillation formats cost-forward per-day lines for a fixture window and tolerates missing keys; `_build_rebalance_input` includes the section when given snapshots and omits it when given none.

## 6. Wire into the rebalance flow (gated by the per-session flag, using the frozen window)

- [x] 6.1 In `ai_portfolio/flows/rebalance.py`, have `run_rebalance_event` fetch outcomes only when the session's `learning_feedback_enabled` is true: read the session's frozen `learning_feedback_window` (falling back to `LEARNING_FEEDBACK_DEFAULT_WINDOW` if an enabled row has a null window), call `list_daily_run_snapshots(..., limit=window)`, and pass the rows to `_build_rebalance_input`; otherwise fetch nothing and pass an empty window. Apply to both the standard and crypto-scoped rebalance paths (shared `_build_rebalance_input`).
- [x] 6.2 Tests (service/flow level): the window is fetched (bounded by the session's window) and threaded when the session flag is on; nothing is fetched and the section is absent when the session flag is off.

## 7. Frontend

- [x] 7.1 Add a learning-feedback opt-in toggle plus a learning-window (days) input to `BuildAIPortfolioCard.tsx` (window pre-filled from the configured default, hidden/disabled while the toggle is off), alongside the technical-indicators / stop-loss / guardrails controls, and send `learning_feedback_enabled` and (when enabled) `learning_feedback_window` with the build request.
- [x] 7.2 Add `learning_feedback_enabled` and `learning_feedback_window` to the session read TS type and surface them on the session detail view as a fact tile (matching the "Risk guardrails" surface: enabled/disabled plus the window when enabled).
- [x] 7.3 Frontend tests: build card sends the flag and window when toggled on, and omits/defaults them when off; session detail shows the enabled/disabled indicator and the window when enabled.

## 8. Verify

- [x] 8.1 Confirm no change to the daily-run snapshot's assembly sequencing/cron, build decisioning, executor sizing, guardrails, session cumulative `total_fees`, or valuation (advisory-only; build only persists the flag and window; the only write-path change is recording the already-computed per-trade fee and surfacing it in the learning document).
- [x] 8.2 Backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` — all green.
- [x] 8.3 Frontend gates: `cd frontend && npm run typecheck && npx vitest run && npm run build` — all green.
- [x] 8.4 Sync the `ai-paper-trading` and `app-shell` spec deltas into the main specs and `openspec validate --specs --strict` passes.
