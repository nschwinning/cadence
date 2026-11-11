## 1. Backend

- [x] 1.1 Add `BotTickRun` model and the `last_failure_at` / `last_failure_error` / `consecutive_failures` columns on `BotSession`, plus an Alembic migration; verify upgrade/downgrade round-trip on a scratch DB and drop `cadence_test`.
- [x] 1.2 Record tick outcomes in `POST /bots/tick` (success via the request session; failure via an independent session, then re-raise; market-closed recorded); add `BOT_TICK_RUN_RETENTION_DAYS=7` / `BOT_TICK_STALE_MINUTES=15` and prune runs older than 7 days in `run_bot_snapshots`; verify with pytest (outcome with processed/failed counts, market-closed row, crashed tick recorded and still 500, prune keeps 6-day and deletes 8-day rows).
- [x] 1.3 Set/clear per-bot failure state in `run_tick` (increment + error on failure after rollback; clear on processed; skipped untouched; flatten failures too) and expose the fields on the bot read schema; verify with pytest (two failing ticks → 2 with message; success clears; skipped keeps).
- [x] 1.4 Add `tick_health` to the dashboard overview (latest run, stale rule, failing bots) and its schema; verify with pytest (healthy, stale when open and 40 min old, never stale when closed, no runs + open = stale, failing bot listed with display name and count, endpoint round-trip).

## 2. Frontend

- [x] 2.1 Types for `tick_health` and the bot failure fields; `HealthSection.tsx` (latest tick, stale and crashed-tick warnings, failing bots linked, consistency counts linking to Admin, all-healthy state, broker-unavailable line) rendered with the Broker account tile in an "Account & health" band; verify with vitest (all healthy, stale, crashed tick, failing bot link/count/error, inconsistency counts, unavailable).
- [x] 2.2 Red failure banner on the bot detail page; verify with vitest (banner with count, time and error; none for a healthy bot).

## 3. Verification

- [x] 3.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 3.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 3.3 `openspec validate add-dashboard-health-section --strict` passes.
