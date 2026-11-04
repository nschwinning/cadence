## 1. Backend — available cash KPI

- [x] 1.1 Add `cash: float` to the `BotKpis` dataclass and populate it from `bot.cash` in `bot_session_kpis` (`strategy_bots/service.py`); verify with a unit test asserting the returned KPIs' `cash` equals the session's cash.
- [x] 1.2 Add `cash: float` to `BotKpisRead` (`api/schemas.py`); verify `GET /api/v1/bots/sessions/{id}/kpis` returns a `cash` field via an API test.

## 2. Backend — session-list current value

- [x] 2.1 Add a service helper (e.g. `bot_current_value(session, bot)`) returning current value by the same rule as `bot_session_kpis`: latest value snapshot's `total_value`, else `total_value(bot, {})` (cost-basis fallback); verify with unit tests for the snapshot and no-snapshot cases.
- [x] 2.2 Add non-optional `current_value: float` to `BotSessionRead` (`api/schemas.py`).
- [x] 2.3 Route all five `BotSessionRead` producers (create/list/get/stop/archive) in `api/routers/bots.py` through one `_to_read(db, row)` helper that does `model_validate(row)` then sets `current_value` from the step 2.1 helper; verify `GET /api/v1/bots/sessions` items each carry `current_value` and a single-session GET also does, via API tests (including the pre-first-snapshot cost-basis case).

## 3. Frontend — detail page available-cash tile

- [x] 3.1 Add `cash: number` to the `BotKpis` type in `frontend/src/types/api.ts`.
- [x] 3.2 In `BotSessionPage.tsx`, add an "Available cash" KPI tile to the Performance section sourced from `kpis.cash`, and remove the now-redundant "Cash" Fact; verify with a component/unit test that the tile renders the cash figure.

## 4. Frontend — overview current value

- [x] 4.1 Add `current_value: number` to the `BotSession`/list type in `frontend/src/types/api.ts`.
- [x] 4.2 In `BotsPage.tsx`, render `current_value` in place of `allocated_capital` in the capital column and update the column header to "Current value"; verify with a test asserting the overview shows the current value (not allocated capital).

## 5. Verify gates

- [x] 5.1 Backend green: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 5.2 Frontend green: `cd frontend && npx vitest run && npx tsc --noEmit`.
