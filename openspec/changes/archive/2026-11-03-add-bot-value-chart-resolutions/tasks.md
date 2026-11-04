# Tasks

## 1. Backend: storage

- [x] 1.1 Add a `BotValuePoint` model in `strategy_bots/models.py` (`bot_value_points`):
  `id` uuid pk, `bot_session_id` fk → `bot_sessions` (indexed), `captured_at` timestamptz,
  `total_value`, `realised_pnl`, `unrealised_pnl` floats; composite index
  `(bot_session_id, captured_at)`. Add the relationship on `BotSession`.
- [x] 1.2 Create an Alembic migration that adds `bot_value_points` and its index
  (reversible: drop table). No change to existing tables.

## 2. Backend: capture at tick

- [x] 2.1 In `_tick_session` (`strategy_bots/service.py`), after the session's marks and
  total value are known for the tick, persist one `BotValuePoint` stamped with the tick
  time (total value = cash + marked positions; realised/unrealised aggregated). Only for
  sessions actually processed — a market-closed tick that processes nothing records no
  points. Keep it additive to the trading path (does not alter position/ledger outcomes).

## 2b. Backend: intraday retention

- [x] 2b.1 Add a `BOT_VALUE_POINT_RETENTION_DAYS = 30` config constant.
- [x] 2b.2 In the daily snapshot job (`run_bot_snapshots`), prune intraday points older
  than the retention window with a single bulk delete
  (`DELETE FROM bot_value_points WHERE captured_at < now - 30 days`) across all sessions.

## 3. Backend: resolution-aware read

- [x] 3.1 Add a `BotValueResolution` enum (`5min`, `hourly`, `daily`, `monthly`).
- [x] 3.2 Add a service function returning a uniform timestamped point list for a session
  at a given resolution: `5min` = raw `bot_value_points` oldest-first; `hourly` = last
  point per clock hour; `daily` = `bot_value_snapshots` mapped to end-of-day timestamps;
  `monthly` = last daily snapshot per calendar month. Downsampling deterministic and
  unit-testable. Empty series when no data.
- [x] 3.3 Update `GET /sessions/{id}/value-history` in `api/routers/bots.py` to accept
  `resolution: BotValueResolution = <default daily>`, keep the `404`, and return the
  points plus the resolution. Update `api/schemas.py` with the timestamped point shape
  (`timestamp`, `total_value`, `realised_pnl`, `unrealised_pnl`) and `resolution` on the
  response. Unknown resolution → `422` (enum validation).

## 4. Frontend: switcher + timestamped chart

- [x] 4.1 Extend `types/api.ts` and `api/bots.ts` with the resolution param and the
  timestamped point/response shape (keep back-compat for existing callers/tests).
- [x] 4.2 In `pages/bots/BotValueChart.tsx`, add a resolution segmented control (5m / 1h /
  1D / 1M), feed the selection into the history query (resolution in the query key),
  and build the series off `timestamp`. Daily/monthly keep carry-forward-to-today;
  intraday resolutions plot raw points without overnight-gap carry-forward. Default
  `daily`. Preserve the "not enough history" placeholder (< 2 points).

## 5. Tests

- [x] 5.1 Backend service: downsampling (`hourly` last-per-hour, `monthly`
  last-per-month), `5min` raw ordering, `daily` snapshot mapping, empty series per
  resolution.
- [x] 5.2 Backend service: a tick persists one intraday point per processed session;
  a market-closed tick persists none; point holds correct total value + P&L.
- [x] 5.2b Backend service: the daily snapshot job prunes intraday points older than 30
  days and keeps points within the window; daily/monthly history is unaffected by pruning.
- [x] 5.3 Backend API (`test_strategy_bots_api.py`): value-history honours each
  resolution; `422` on unknown resolution; `404` on unknown session; empty series ok.
- [x] 5.4 Frontend (`BotValueChart.test.tsx`): switcher renders; changing resolution
  refetches with the new param; timestamped series builds; empty/placeholder states.

## 6. Verify

- [x] 6.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`
- [x] 6.2 Frontend: `cd frontend && npx vitest run && npx tsc --noEmit`
- [x] 6.3 `openspec validate add-bot-value-chart-resolutions --strict`
