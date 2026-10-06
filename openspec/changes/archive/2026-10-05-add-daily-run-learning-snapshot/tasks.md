## 1. Data model + migration

- [x] 1.1 Add a `SessionDailyRunSnapshot` ORM model in `paper_trading/models.py` (or `ai_portfolio/models.py` alongside the assembler — pick the module whose service owns assembly): columns `id`, `session_id` (FK → `paper_trading_sessions`, SET NULL, indexed), `portfolio_id` (nullable FK → `portfolios`, SET NULL, indexed), `run_date` (`Date`, indexed), `ai_portfolio_event_id` (nullable FK → `ai_portfolio_events`, SET NULL), `document` (JSONB), `created_at`, `updated_at`, and a unique constraint on `(session_id, run_date)`; verify `uv run mypy src/cadence` passes with the new model.
- [x] 1.2 Create an Alembic migration whose `down_revision` is the current live head (confirm with `uv run alembic heads`; expected `c7d8e9f0a1b2`) that creates `session_daily_run_snapshots` with the indexes, unique constraint, and SET-NULL FKs; verify `uv run alembic upgrade head`, then `downgrade -1`, then `uv run alembic check` reports no drift.

## 2. Assembly service

- [x] 2.1 Implement a helper that, for a given session and `run_date`, locates that day's rebalance `AIPortfolioEvent` (most recent event whose `created_at` falls on `run_date` in the snapshot timezone, or `None`) and builds the consolidated `document` from the run (`result_payload`, `trend_context`, `run_stats`, `status`, `event_type`, `duration_ms`, `error`), the reconciled `PaperTrade` rows for that session/day (`ticker, side, quantity, price, notional, order_id, order_status, filled_price, filled_at, executed_at`), and the day's `SessionValueSnapshot` (`total_value, cash_value, positions_value, daily_pnl, daily_pnl_pct, positions`); verify a unit test asserts the document shape for a day with a run.
- [x] 2.2 Implement `assemble_daily_run_snapshots(session, ...)` in `ai_portfolio/service.py` that selects the day's sessions using the same selection semantics as `snapshot_all_sessions` (active AI-managed; weekend crypto-scope gating), assembles each session that has a `SessionValueSnapshot` for the day, upserts one row per `(session_id, run_date)` (update in place on re-run), and is best-effort per session (log and continue on one session's failure); verify a unit test covering multi-session assembly where one session raises and the rest still persist.
- [x] 2.3 Handle the no-rebalance-run day: a session with a value snapshot but no event for the day records a row with `ai_portfolio_event_id = None`, `document.run = None`, `document.orders = []`, and the valuation populated; a session with no value snapshot for the day is skipped (no row); verify unit tests for both cases.
- [x] 2.4 Make assembly idempotent per session per day: re-running on the same `run_date` updates the existing row rather than inserting a duplicate; verify a unit test that runs assembly twice and asserts a single row reflecting the latest run.

## 3. Cron-guarded endpoint

- [x] 3.1 Add a cron-token-guarded `POST /api/v1/ai-portfolio/daily-run-snapshot` endpoint that validates the shared cron-token secret (reject missing/invalid with the same status as `/ai-portfolio/snapshot-daily`) and calls `assemble_daily_run_snapshots`; verify an API test that a valid token assembles rows and an invalid/missing token is rejected and records nothing.

## 4. Backend-only guarantee

- [x] 4.1 Confirm the learning snapshot is exposed through no read schema, read API, or frontend: do not add it to `AIPortfolioEventRead` or any paper-trading read model; verify by grep that `session_daily_run_snapshots` / `SessionDailyRunSnapshot` appears in no `api/schemas.py` read model and in no frontend `types/api.ts`.

## 5. Verification

- [x] 5.1 Run the full backend gate from `backend/`: `uv run ruff check . && uv run mypy src/cadence && uv run pytest` — all green.
- [x] 5.2 Re-run the migration round-trip (`uv run alembic upgrade head`, `downgrade -1`, `upgrade head`, `uv run alembic check`) to confirm no drift after all code is in place.
