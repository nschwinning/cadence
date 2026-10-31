## 1. Scheduling mode and build params

- [x] 1.1 Add `WEEKLY_REBALANCING` and `MONTHLY_REBALANCING` members to `ScheduleMode` (`backend/src/cadence/paper_trading/constants.py`), values `"WEEKLY_REBALANCING"` / `"MONTHLY_REBALANCING"`. Add a small helper mapping between the user-facing cadence string (`daily`/`weekly`/`monthly`) and the three rebalancing `ScheduleMode` members, treating any other/legacy mode as `daily`.
- [x] 1.1a Widen `paper_trading_sessions.schedule_mode` from `VARCHAR(17)` to `VARCHAR(32)` via an Alembic migration (the new enum values are 18–19 chars and overflow the original column). Round-trip the migration (upgrade/downgrade) and apply it to any persistent database.
- [x] 1.2 Add a `rebalance_cadence` field to `AIBuildParams` (`backend/src/cadence/ai_portfolio/params.py`) defaulting to `daily`; thread it through `to_payload`/`from_payload` (round-trips, missing key ⇒ `daily`).
- [x] 1.3 In `backend/src/cadence/ai_portfolio/flows/build.py`, map the chosen `rebalance_cadence` to the session's `schedule_mode` instead of hardcoding `ScheduleMode.DAILY_REBALANCING`; unspecified ⇒ daily.

## 2. Due-check and cron targeting

- [x] 2.1 Add a pure, unit-testable `rebalance_due(schedule_mode, last_rebalanced_at, now, tz)` helper: daily ⇒ always due; `last_rebalanced_at is None` ⇒ due; weekly ⇒ ISO (year, week) of `now` differs from `last_rebalanced_at` in ET; monthly ⇒ (year, month) differs in ET.
- [x] 2.2 Add an anchor helper that returns the session's latest **succeeded** rebalance AI-portfolio event timestamp (or `None` when never allocated), derived from existing event history (no new column). Confirm a market-closed/failed run does not advance the anchor.
- [x] 2.3 In `rebalance_daily` (`backend/src/cadence/api/routers/ai_portfolio.py`), broaden targeting to `schedule_mode in {DAILY, WEEKLY, MONTHLY}_REBALANCING` and apply the due-check after the already-running and awaiting-build-fill checks; skip not-yet-due sessions.
- [x] 2.4 Add a `skipped_not_due` bucket to `AIDailyRebalanceResponse` (session ids), populated for sessions skipped only because their cadence is not yet due.
- [x] 2.5 Confirm `rebalance_crypto_daily` keeps its existing `schedule_mode == DAILY_REBALANCING` filter so weekly/monthly sessions are excluded from the weekend crypto trigger; add a brief comment documenting this as the intentional single-rebalance-per-period guarantee.

## 3. Read model and schemas

- [x] 3.1 Add an optional `rebalance_cadence` (default `daily`) to the AI build request schema (`backend/src/cadence/api/schemas.py`); thread it into `AIBuildParams` in the router/build entry point.
- [x] 3.2 Add `rebalance_cadence` to `PaperTradingSessionRead`, derived from `schedule_mode` via the step 1.1 mapping (legacy/other ⇒ `daily`); set it in the explicit router mapping.

## 4. Frontend

- [x] 4.1 Add a **required** rebalance-cadence radio group (Daily / Weekly / Monthly, **no option pre-selected**) to `frontend/src/pages/portfolios/BuildAIPortfolioCard.tsx`; block form submission until the user selects exactly one.
- [x] 4.2 Add `rebalance_cadence` to the build request type/call in `frontend/src/api/aiPortfolio.ts` and to the session read type in `frontend/src/types/api.ts`.
- [x] 4.3 Add a "Rebalance cadence" fact tile to the session-detail view, mirroring the existing model/guardrails/fundamentals tiles; default display to Daily when unrecorded.

## 5. Tests

- [x] 5.1 Backend unit tests: `ScheduleMode` round-trips the two new values; `AIBuildParams` cadence round-trips through `to_payload`/`from_payload` (default daily).
- [x] 5.2 Backend unit tests for `rebalance_due`: daily always due; weekly due only across an ISO-week boundary; monthly due only across a calendar-month boundary; never-allocated ⇒ due; weekend/holiday month-start fires on the first trading-day run; ET boundary correctness.
- [x] 5.3 Backend tests: build persists the chosen `schedule_mode` for each cadence; `rebalance_daily` includes due weekly/monthly sessions, reports not-yet-due ones under `skipped_not_due`, and leaves existing daily behavior unchanged; `rebalance_crypto_daily` excludes weekly/monthly sessions.
- [x] 5.4 Backend test: `PaperTradingSessionRead.rebalance_cadence` reflects each `schedule_mode` and defaults to daily for legacy/other modes.
- [x] 5.5 Frontend Vitest: cadence radio group has no pre-selected option and blocks submission until one is chosen; submitting sends the selected cadence with the build request; session-detail tile renders the cadence (and defaults to Daily when unrecorded).

## 6. Verify

- [x] 6.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 6.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 6.3 `openspec validate add-rebalance-cadence-options --strict`.
