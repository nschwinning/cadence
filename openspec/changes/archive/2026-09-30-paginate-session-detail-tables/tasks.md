## 1. Backend — AI events read (bring up to wrapped shape)

- [x] 1.1 Add `AIPortfolioEventListResponse` (`items: list[AIPortfolioEventRead]`, `total: int`) to `api/schemas.py`, mirroring `AIPortfolioRunListResponse`.
- [x] 1.2 Add `count_session_events(session, session_id) -> int` to `ai_portfolio/service.py` (mirror `count_session_runs`), and add `offset: int = 0` to `list_session_events` applied as `.offset(offset)` alongside the existing `.limit(...)`.
- [x] 1.3 Update the `list_session_events` router (`api/routers/ai_portfolio.py`) to accept `offset: int = Query(ge=0) = 0`, change its `response_model` to `AIPortfolioEventListResponse`, and return `{items, total}` (items from `list_session_events(..., limit, offset)`, total from `count_session_events`).
- [x] 1.4 Verify: an API test asserts the events endpoint returns `{items,total}`, honors `limit`+`offset` (page window + correct total), and returns an empty `items` with the true `total` when `offset` is at/beyond the end.

## 2. Backend — add offset to the three already-wrapped reads

- [x] 2.1 Add `offset: int = 0` to `get_session_trades`, `get_closed_positions`, and `get_session_runs` in `paper_trading/service.py`, applied as `.offset(offset)` alongside the existing `.limit(...)`; keep each existing default `limit`. Do NOT touch the unbounded `list_closed_position_pnls`.
- [x] 2.2 Add `offset: int = Query(ge=0) = 0` to `list_session_trades`, `list_session_positions`, and `list_session_runs` in `api/routers/paper_trading.py` and pass it through to the service; responses stay `PaperTradeListResponse` / `ClosedPositionListResponse` / `SessionRunListResponse`.
- [x] 2.3 Verify: API tests assert each of the three endpoints honors `limit`+`offset` (returns the requested window with the unchanged full `total`) and returns an empty page with the true total past the end.

## 3. Frontend — API clients, hooks, and query keys

- [x] 3.1 Add an `AIPortfolioEventListResponse` type (`{items, total}`) to the frontend types; change `listSessionEvents(sessionId, {limit, offset})` in `api/aiPortfolio.ts` to send both params and return the wrapped response; make `aiPortfolioKeys.sessionEvents(sessionId, offset)` include the offset; update `useSessionEvents(sessionId, offset)` accordingly.
- [x] 3.2 In `api/paperTrading.ts`, thread `{limit, offset}` into `listSessionTrades` / `listSessionRuns` / `listSessionPositions`, include the offset in `paperTradingKeys.trades/runs/positions(sessionId, offset)`, and update `useSessionTrades` / `useSessionRuns` / `useSessionPositions` to take and pass the offset.
- [x] 3.3 Confirm `useSessionOrderSync` invalidation still targets the trades/positions key prefixes so the currently-viewed page refetches (invalidate by the session-scoped key prefix, not an exact offset key).

## 4. Frontend — page-through UI

- [x] 4.1 Add a shared presentational `Pagination` control (prev/next buttons + a "Page X of N" / "showing … of total" indicator; prev disabled on the first page, next disabled on the last; conveys single-page state), computing total pages from the server `total` and the table's page size.
- [x] 4.2 Add fixed page-size constants (5 for events & runs, 10 for trades & closed positions) and per-panel `page` state in `PaperTradingSessionPage.tsx`; wire each of `EventsPanel`, `TradesPanel`, `RunsPanel`, `PositionsPanel` to pass `offset = page * pageSize` to its hook and render the `Pagination` control. Paging one panel must not affect the others.
- [x] 4.3 Switch `EventsPanel` from `events.length` to the server `total`. Clamp/disable next when the current page is the last derived from `total`.
- [x] 4.4 Verify: vitest covers the `Pagination` control (disabled edges, page/total display, single-page state) and that each panel requests the next page's offset on "next" and shows the server total.

## 5. Verification

- [x] 5.1 Backend: `uv run pytest`, `uv run ruff check .`, `uv run mypy src/cadence` all green.
- [x] 5.2 Frontend: `npm run typecheck`, `npx vitest run`, `npm run build` all green.
- [x] 5.3 `openspec validate paginate-session-detail-tables --strict` passes.
