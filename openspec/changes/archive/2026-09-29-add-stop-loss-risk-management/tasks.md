# Tasks

## 1. Settings & constants

- [x] 1.1 Add `STOP_LOSS_DEFAULT_PCT` (e.g. 0.15) and `STOP_LOSS_COOLDOWN_TRADING_DAYS` (default 5) to `settings`, and verify they load with sane defaults via a settings import test
- [x] 1.2 Add a `stop_loss` `signal_type` value and a `stop_loss` `SessionRun` trigger value to the relevant `constants.py` enums, and verify existing enum tests still pass with the new members

## 2. Data model & migration

- [x] 2.1 Add non-nullable `stop_loss_enabled` (server_default false) and nullable `stop_loss_pct` columns to the `PaperTradingSession` model, and add a `StopLossQuarantine` model (`id`, `session_id` FK, `ticker`, `excluded_until`, `created_at`; index on `(session_id, ticker)`); verify the models import and the test create_all builds the schema
- [x] 2.2 Write one Alembic migration on the current single head adding the two session columns (backfilled off) and creating the `stop_loss_quarantines` table; verify `alembic upgrade head` then `downgrade` round-trips and `alembic check` reports no drift
- [x] 2.3 Drop `cadence_test` so the test schema is rebuilt with the new columns/table, and verify the suite recreates it cleanly

## 3. Brokerage: batched multi-symbol quotes

- [x] 3.1 Make `AlpacaBroker.get_quotes` fetch equities and crypto in batched comma-separated multi-symbol requests (keeping the per-symbol fallback), and verify a unit test that a multi-symbol call issues batched requests and returns a quote per symbol
- [x] 3.2 Ensure the `StubBroker.get_quotes` returns quotes for a multi-symbol request so offline/stub scans work, and verify via a stub unit test

## 4. Build: persist & freeze the stop-loss setting

- [x] 4.1 Add `stop_loss_enabled` and optional `stop_loss_pct` to `AIPortfolioBuildRequest` (schemas), defaulting the threshold to `STOP_LOSS_DEFAULT_PCT` when enabled without one; verify a schema/validation test
- [x] 4.2 Persist the (frozen) stop-loss opt-in and threshold on the session during build in `ai_portfolio/service.py`; verify a build test that an opted-in build stores enabled+threshold and a default build stores disabled

## 5. Stop-loss scan, evaluation & execution

- [x] 5.1 Implement a service routine that iterates all active opted-in sessions, dedups the union of held tickers, fetches batched quotes, and for each held position computes the trigger `avg_cost × (1 − stop_loss_pct)` from the ledger; verify a unit test that a below-trigger position is selected and an above-trigger one is not
- [x] 5.2 Sell breached positions through the existing executor sell path with `signal_type=stop_loss` and no AI-event reference, recording the trade, a `stop_loss` `SessionRun`, a closed position with realized P&L, and the transaction cost; verify a test asserting the recorded trade/run/closed-position shape and that `total_fees` increased
- [x] 5.3 Guard equity sells by market status (only when open) while allowing crypto sells anytime, and leave a position unchanged when its quote is missing; verify tests for the market-closed equity defer, the crypto anytime sell, and the missing-quote skip
- [x] 5.4 Wrap per-session and per-position processing so one failure does not abort the scan; verify a test that a failing session does not prevent a later session from being stopped out

## 6. Cooldown quarantine

- [x] 6.1 On each stop-out, write a `StopLossQuarantine` row with `excluded_until` = `STOP_LOSS_COOLDOWN_TRADING_DAYS` ahead; verify a test that a stop-out creates the row with the expected expiry
- [x] 6.2 Exclude candidate tickers the session does not hold whose quarantine is unexpired from the rebalance candidate assembly (regardless of trend opt-in), and stop excluding once expired; verify a rebalance test that a freshly quarantined ticker is absent from candidates and an expired one reappears

## 7. Notifications

- [x] 7.1 Send a best-effort Pushover notification per stop-out (best-effort: a send failure is logged and does not roll back the sale); verify a test that a stop-out triggers a notification and that a notification failure still leaves the sale recorded

## 8. Cron endpoint

- [x] 8.1 Add a cron-token-guarded router endpoint that runs the stop-loss scan across all opted-in sessions in the background and returns immediately; verify tests that a valid token triggers the scan and a missing/invalid token is rejected without selling

## 9. Read model

- [x] 9.1 Expose `stop_loss_enabled` and `stop_loss_pct` on `PaperTradingSessionRead` (list + detail); verify a test that the session read includes the stop-loss configuration

## 10. Frontend

- [x] 10.1 Mirror the new fields in `types/api.ts` (build request + session read); verify `npm run typecheck` passes
- [x] 10.2 Add a default-off stop-loss toggle and threshold input to the AI build form, sending them with the build request; verify a Vitest test that enabling the toggle sends the opt-in + threshold and leaving it off sends it disabled
- [x] 10.3 Show the session's stop-loss configuration on the session detail view and make stop-loss trades/runs identifiable as stop-loss activity; verify Vitest tests for the config display and the stop-loss labelling

## 11. Verification

- [x] 11.1 Run `uv run ruff check . && uv run mypy src/cadence && uv run pytest` and confirm all green
- [x] 11.2 Run `npm run typecheck && npx vitest run && npm run build` in the frontend and confirm all green
- [x] 11.3 Run `openspec validate add-stop-loss-risk-management --strict` and confirm it passes
