## Why

The paper-trading session-detail page renders four tables — AI portfolio events, paper trades, closed positions, and session runs — each fetched as a single capped list (limit 20/100/100/50). As a session accumulates history the page loads and renders a large, ever-growing block per table, and older rows silently fall off the cap with no way to reach them. Three of the four read endpoints already return a wrapped `{items, total}` shape with a matching `count_*` function; they simply lack an `offset`, so the total is displayed but the rows past the first page are unreachable. The AI-events endpoint is worse: it returns a bare list with no total at all, so its panel shows only the loaded count, not the true number of events.

## What Changes

- Add **server-side, page-through pagination** (explicit prev/next controls — no infinite scroll) to all four session-detail tables, with **fixed default page sizes**: 5 for AI events and session runs, 10 for trades and closed positions.
- Page 1 shows the most-recent page of rows (existing ordering is newest-first); users can browse older pages and see "page X of N" / total context.
- Thread an `offset` parameter through the three already-wrapped reads (trades, closed positions, runs) and their services.
- Bring the AI-events read up to the same shape: a new `{items, total}` response wrapper, a new per-session count function, and an `offset` parameter.
- No new persistence, migration, or configuration — this is a read-path + UI change only. The unbounded closed-position P&L read used by session KPIs stays unbounded (it is not a paginated feed).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ai-paper-trading`: the per-session AI-events read gains a wrapped `{items, total}` response and offset-based pagination; the trades, closed-positions, and session-runs reads gain offset-based pagination over their existing wrapped responses.
- `app-shell`: the session-detail page presents each of the four tables one fixed-size page at a time with page-through navigation instead of a single capped list.

## Impact

- **Backend** — `api/routers/ai_portfolio.py` (`list_session_events`), `ai_portfolio/service.py` (`list_session_events` + new `count_session_events`), `api/routers/paper_trading.py` (`list_session_trades`, `list_session_positions`, `list_session_runs`), `paper_trading/service.py` (`get_session_trades`, `get_closed_positions`, `get_session_runs`), `api/schemas.py` (new `AIPortfolioEventListResponse`).
- **Frontend** — `api/aiPortfolio.ts` (`listSessionEvents`, `useSessionEvents`, event query key + a new event-list response type), `api/paperTrading.ts` (`listSessionTrades`/`listSessionRuns`/`listSessionPositions` + their hooks + query keys), and `pages/paper-trading/PaperTradingSessionPage.tsx` (`EventsPanel`, `TradesPanel`, `RunsPanel`, `PositionsPanel` + a new page-through control). Paging state must live inside each react-query key so the existing `useSessionOrderSync` invalidation still refetches the currently-viewed page.
- **No** database migration, config, or DB schema change.
