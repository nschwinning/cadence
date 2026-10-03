## 1. Backend: sector/category performance aggregation (D1, D2, D3, D4)

- [x] 1.1 Add a service function in `paper_trading/service.py` that, for a session id, collects the distinct tickers across open positions (`list_open_positions`) and closed positions (`get_closed_positions`), normalises them with `normalize_ticker`, and fetches `Asset.ticker, Asset.category, Asset.sector` for those tickers in a single query; verify a unit test that the join matches tickers regardless of stored casing.
- [x] 1.2 In that function, mark open positions to market via `compute_session_value()` and aggregate per sector and per category: `realized_pnl` (sum of `ClosedPosition.realized_pnl`), `unrealized_pnl` (sum of open positions' `unrealised_pnl`), `total_pnl` (= realised + unrealised), `market_value` (sum of open positions' `market_value`), and `return_pct` = `total_pnl / cost_basis` where cost basis = Σ(`market_value − unrealised_pnl`) for open + Σ closed cost basis; verify a test that `total_pnl` equals realised + unrealised for a mixed group.
- [x] 1.3 Bucket a null `Asset.sector` under a "No sector" key in the by-sector grouping only (reuse the `NO_SECTOR_KEY` convention), keeping the asset's category intact in the by-category grouping; verify a test that a crypto holding lands in "No sector" by sector but under its category by category.
- [x] 1.4 Bucket a position ticker with no matching `Asset` under an "Unknown" key in both groupings, and assert in a test that group totals still sum to the session's overall realised + unrealised P&L (no P&L dropped).
- [x] 1.5 Guard the per-group return against a zero cost basis by returning `None` (unavailable) instead of dividing; verify a test covers the zero-cost-basis group.
- [x] 1.6 Raise the standard not-found error for an unknown session id; verify a test asserts the not-found path.

## 2. Backend: schema + endpoint (D6)

- [x] 2.1 Add `SessionGroupPerformance { key: str, market_value, realized_pnl, unrealized_pnl, total_pnl, return_pct: float | None }` and a response schema `{ by_sector: list[...], by_category: list[...] }` to `api/schemas.py`; verify `uv run mypy src/cadence` passes.
- [x] 2.2 Add `GET /paper-trading/sessions/{id}/sector-performance` to `api/routers/paper_trading.py` calling the new service function, returning the response schema, and mapping unknown session → 404; verify router tests cover a populated session and the 404 case.

## 3. Frontend: types + client hook (D5, D6)

- [x] 3.1 Add the `SessionGroupPerformance` and response types to `frontend/src/types/api.ts`; verify `npm run typecheck` passes.
- [x] 3.2 Add a typed client + query hook for the new endpoint to `frontend/src/api/paperTrading.ts`, keyed by session id; verify typecheck passes.

## 4. Frontend: session-detail performance card (D5)

- [x] 4.1 Add a performance card to `pages/paper-trading/PaperTradingSessionPage.tsx` (alongside the KPI grid / above the positions panel) with a by-sector / by-category toggle, rendering per-group rows/diverging bars with total P&L coloured by sign and the return %; verify it renders from a fixture.
- [x] 4.2 Render the "not available" state for a group whose `return_pct` is null, and an empty state when both groupings are empty; verify a co-located Vitest test covers signed P&L, the unavailable-return state, and the empty state.

## 5. Verification

- [x] 5.1 Backend: `uv run ruff check . && uv run mypy src/cadence && uv run pytest` all green.
- [x] 5.2 Frontend: `npm run typecheck && npx vitest run && npm run build` all green.
- [x] 5.3 `openspec validate add-session-sector-performance --strict` passes.
