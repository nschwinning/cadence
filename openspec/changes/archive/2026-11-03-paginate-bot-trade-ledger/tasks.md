# Tasks

## 1. Backend: paginated trade query

- [x] 1.1 Add a service function in `strategy_bots/service.py` (e.g.
  `list_bot_trades_page(session, bot, *, limit, offset)`) that returns `(items, total)`:
  a `SELECT` on `BotTrade` filtered by `bot_session_id`, ordered by `created_at` desc
  then `id` desc, with `LIMIT`/`OFFSET`, plus a separate `count(*)` for the total. Do
  not load the full `trades` relationship.
- [x] 1.2 Update `GET /sessions/{id}/trades` in `api/routers/bots.py` to accept
  `limit: int = Query(20, ge=1, le=100)` and `offset: int = Query(0, ge=0)`, resolve
  the session (keep the `404`), call the new service function, and return
  `BotTradeListResponse(items=…, total=…)` with `total` as the full count.

## 2. Frontend: pagination controls

- [x] 2.1 In `pages/bots/BotSessionPage.tsx`, add page state and pass `limit`/`offset`
  to the trades query (include the page in the query key so pages cache independently).
- [x] 2.2 Render pagination controls under the trades table: Previous (disabled on page
  0), Next (disabled when the last page is reached), and a "Page X of N" indicator
  derived from `total` and the page size. Preserve most-recent-first ordering and the
  existing empty state when `total === 0`.

## 3. Tests

- [x] 3.1 Backend (`backend/tests/test_strategy_bots_api.py`): default page returns at
  most the default size with `total` = full count; `offset`/`limit` select the correct
  window; ordering is most-recent-first and stable; `422` on negative offset/limit and
  on limit > 100; `404` on unknown session.
- [x] 3.2 Backend service test for `list_bot_trades_page` (ordering, window, total)
  against seeded trades.
- [x] 3.3 Frontend (`BotSessionPage.test.tsx`): controls render; Next/Previous advance
  the page and refetch with the new offset; buttons disable at the first/last page;
  empty state preserved.

## 4. Verify

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`
- [x] 4.2 Frontend: `cd frontend && npx vitest run && npx tsc --noEmit`
- [x] 4.3 `openspec validate paginate-bot-trade-ledger --strict`
