## 1. Backend — best/worst closed round-trip

- [x] 1.1 In `strategy_bots/service.py`, add a `TradeExtreme` shape (ticker + realised_pnl) and a `bot_trade_extremes(bot)` helper that walks the session's trades chronologically, pairs each sell with its ticker's open entry basis, computes each closed round-trip's realized P&L (`(sell_price - entry_price) * qty - entry_fees - sell_fees`), and returns the best (max) and worst (min) round-trip or `None` when there are no closed round-trips. Verify a new unit test in `backend/tests/test_strategy_bots_service.py` covers: a single closed round-trip (best == worst), a multi-ticker mix with a clear best and worst, still-open positions excluded, and the no-closed-trade case returning `None`/`None`.
- [x] 1.2 Add `best_trade` and `worst_trade` (optional `TradeExtreme`) fields to the `BotKpis` dataclass and populate them in `bot_session_kpis` from `bot_trade_extremes`. Verify `test_strategy_bots_service.py` asserts the KPIs carry the expected best/worst trade for a session with closed round-trips and `None` for one without.
- [x] 1.3 Add `best_trade`/`worst_trade` (optional, with `ticker` and `realised_pnl`) to `BotKpisRead` in `api/schemas.py` so the `/kpis` endpoint serializes them. Verify `backend/tests/test_strategy_bots_api.py` asserts the kpis response includes best/worst trade for a session with a closed round-trip.
- [x] 1.4 Run `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` and verify all pass.

## 2. Frontend — best/worst trade tile

- [x] 2.1 In `frontend/src/types/api.ts`, extend `BotKpis` with optional `best_trade` and `worst_trade` (`{ ticker: string; realised_pnl: number } | null`). Verify `npx tsc --noEmit` passes.
- [x] 2.2 In `BotSessionPage.tsx`, render a best/worst trade tile in the Performance section (ticker + realized P&L for each, signed/coloured like other P&L figures; show a "no closed trades yet" state when both are absent). Verify `BotSessionPage.test.tsx` asserts the tile renders the best and worst trade for a session with closed trades and the empty state when absent.

## 3. Frontend — open-positions sort control

- [x] 3.1 In `BotSessionPage.tsx`, add a sort control to the open-positions table offering "Ticker" (default) and "Opened" orderings, re-sorting the in-memory positions array accordingly (ticker default preserves current behavior). Verify `BotSessionPage.test.tsx` asserts the default order is by ticker and that choosing "Opened" reorders rows by `opened_at`.

## 4. Frontend gates

- [x] 4.1 Run `cd frontend && npx vitest run && npx tsc --noEmit` and verify all pass.
