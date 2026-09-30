## Context

See proposal.md — Why. The session-detail page (`frontend/src/pages/paper-trading/PaperTradingSessionPage.tsx`) renders four tables, each backed by a single list read:

- Trades — `GET /api/v1/paper-trading/sessions/{id}/trades` → `PaperTradeListResponse {items,total}`, service `get_session_trades(limit=100)`, `count_session_trades` exists.
- Closed positions — `GET .../positions` → `ClosedPositionListResponse {items,total}`, service `get_closed_positions(limit=100)`, `count_closed_positions` exists.
- Runs — `GET .../runs` → `SessionRunListResponse {items,total}`, service `get_session_runs(limit=50)`, `count_session_runs` exists.
- AI events — `GET /api/v1/ai-portfolio/sessions/{id}/events` → **bare `list[AIPortfolioEventRead]`**, service `list_session_events(limit=20)`, **no total, no count function**.

The repo already has the target server-side paging shape: `GET /api/v1/ai-portfolio/runs` (`list_ai_runs(limit, offset)` + `count_ai_runs`, wrapped `{items,total}`) and `GET /api/v1/assets`. The only offset-driven UI today (assets) uses `useInfiniteQuery` / infinite scroll, which is explicitly not wanted here.

None of the four table hooks poll, but `useSessionOrderSync` (1500 ms while orders are non-terminal) invalidates the trades and positions query keys on each reconcile.

## Goals / Non-Goals

**Goals:**
- One consistent server-side `limit`+`offset`+`{items,total}` read shape across all four tables.
- Fixed default page sizes: 5 (events, runs), 10 (trades, closed positions).
- Explicit prev/next page-through UI, first page = most recent rows.

**Non-Goals:**
- No user-adjustable page size (fixed defaults only).
- No infinite scroll.
- No change to ordering, persistence, migrations, or config.
- No pagination of the KPI-only unbounded `list_closed_position_pnls` read.
- No cursor/keyset pagination — offset paging matches the existing repo pattern and the per-session row counts are small.

## Decisions

### 1. Bring AI events up to the wrapped `{items,total}` shape
The events endpoint is the only outlier. Add:
- `AIPortfolioEventListResponse {items: list[AIPortfolioEventRead], total: int}` in `api/schemas.py` (mirrors `AIPortfolioRunListResponse`).
- `count_session_events(session, session_id) -> int` in `ai_portfolio/service.py` (mirrors `count_session_runs`).
- `offset` param on `list_session_events` (service + router) and change the router `response_model` to the new wrapper.

*Alternative considered:* leave events as a bare list and paginate client-side. Rejected — it keeps the one inconsistent endpoint inconsistent, and the panel would still lack a true total (today it shows `events.length`).

### 2. Add `offset` to the three already-wrapped reads; keep default `limit` values
Each of `get_session_trades` / `get_closed_positions` / `get_session_runs` gains `offset: int = 0` applied as `.offset(offset)` alongside the existing `.limit(...)`; routers add `offset: int = Query(ge=0) = 0`. Service default `limit` values stay as-is (back-compat for any non-paged caller); the frontend passes the page sizes explicitly. `count_*` functions already exist and are unchanged.

The `get_closed_positions` default limit of 100 is unchanged; the frontend simply requests `limit=10`. The unbounded `list_closed_position_pnls` (KPIs) is left exactly as-is.

### 3. Page state lives in React + inside each query key
Each panel owns a `page` (or `offset`) state. `offset = page * pageSize` is threaded into the client fn and — critically — into the react-query key (e.g. `paperTradingKeys.trades(sessionId, offset)`), so `useSessionOrderSync`'s invalidation still refetches the *currently viewed* page. Fixed page sizes are module constants, not state.

*Alternative considered:* keep the key session-scoped and refetch all pages. Rejected — page must be part of the cache identity for both correct caching and correct invalidation.

### 4. One shared page-through control component
No shared pagination control exists. Add a small presentational `Pagination` (prev/next buttons + "Page X of N" / "showing … of total") used by all four panels. Total pages derived from the server `total` and the table's page size; prev disabled on page 0, next disabled on the last page. `EventsPanel` switches from `events.length` to the server `total`.

*Alternative considered:* inline controls per panel. Rejected — four near-identical copies; a shared component keeps behavior and a11y consistent.

### 5. First page = most recent
Reads already return newest-first, so `offset = 0` is the most recent page; no ordering change needed. Paging walks backward in time via increasing offset.

## Risks / Trade-offs

- **Offset drift when new rows arrive between page views** (a new trade shifts rows by one) → Acceptable: these tables change rarely during viewing, and order-sync invalidation refetches the current offset. Not worth cursor pagination for small per-session counts.
- **A page landing empty after rows are removed/at a stale high offset** → The UI derives the max page from the server `total` on each fetch and clamps/disables next accordingly; the spec requires an offset past the end to return an empty page with the true total, so the control can recover.
- **Changing the events `response_model` from a bare list to a wrapper is a breaking read-shape change** → Only the frontend consumes it, and it is updated in the same change; there is no external API contract to preserve.

## Migration Plan

None. No schema, migration, or config changes. Backend `limit` defaults are preserved so nothing outside the updated frontend needs to change. Deploy backend and frontend together (the events response shape changes); rollback is a plain revert.
