## 1. Backend — valuation + Sharpe primitives

- [x] 1.1 Add `SHARPE_TRADING_DAYS_PER_YEAR = 252` and `SHARPE_MIN_RETURNS = 20` to `paper_trading/constants.py`; add a settings-backed risk-free rate defaulting to `0.0`. Verify by importing the constants in a test.
- [x] 1.2 Add a top-level `unrealized_pnl: float` field to the `SessionValuation` dataclass and populate it inside `compute_session_value` from the summed per-position marks (`unrealized_total`). Verify with a service test asserting `valuation.unrealized_pnl` equals the sum of the per-position `unrealized_pnl`.
- [x] 1.3 Implement a pure `sharpe_ratio(returns, *, risk_free=0.0) -> float | None` in `paper_trading/service.py` (mean-over-sample-stdev × √`SHARPE_TRADING_DAYS_PER_YEAR`, excess of `risk_free`); return `None` when `len(returns) < SHARPE_MIN_RETURNS` or stdev is 0. Verify with unit tests: a known series → known value, `None` below the minimum count, `None` when stdev is 0.

## 2. Backend — KPI service + endpoint

- [x] 2.1 Add a `session_kpis(session, *, session_id, broker)` service function that loads the session (raising `SessionNotFoundError` if absent), calls `compute_session_value`, reads `total_pnl`, computes `total_return = current_value - allocated_capital` and `total_return_pct = total_return / allocated_capital`, and calls `sharpe_ratio` on the ordered `daily_pnl_pct` series from `list_value_snapshots`. Verify with a service test over a stubbed broker valuation (asserting `total_return` equals realised + unrealised P&L).
- [x] 2.2 Add `PaperTradingSessionKpisRead` to `api/schemas.py` with `current_value`, `realised_pnl`, `unrealised_pnl`, `total_return`, `total_return_pct`, and `sharpe_ratio: float | None`. Verify the schema imports and validates a sample dict.
- [x] 2.3 Add `GET /api/v1/paper-trading/sessions/{id}/kpis` to `api/routers/paper_trading.py` injecting the broker DI, calling `session_kpis`, mapping `SessionNotFoundError -> 404`, and returning `PaperTradingSessionKpisRead`. Verify with API tests: the five fields returned for an existing session (stubbed broker), and 404 for an unknown session id.

## 3. Frontend — data layer

- [x] 3.1 Add shared `formatCurrency` and `formatPercent` helpers to `lib/format.ts`; add a co-located Vitest covering currency and percent formatting (including negative and zero). Verify the Vitest passes.
- [x] 3.2 Add a `PaperTradingSessionKpis` type to `types/api.ts` mirroring `PaperTradingSessionKpisRead` (`current_value`, `realised_pnl`, `unrealised_pnl`, `total_return`, `total_return_pct`, `sharpe_ratio: number | null`). Verify `npm run typecheck` passes.
- [x] 3.3 Add `paperTradingKeys.kpis(sessionId)`, a `getSessionKpis` fetcher, and a `useSessionKpis(sessionId)` hook (enabled only when `sessionId` is non-empty) to `api/paperTrading.ts`. Verify with a hook/key test.

## 4. Frontend — KPI tiles on the session page

- [x] 4.1 Render a KPI tile row on `PaperTradingSessionPage.tsx` using `StatTile` for current value, realised P&L, unrealised P&L, total return, and Sharpe; colour realised/unrealised/total-return by sign via the existing `pnlClass()`, and adopt the shared formatters. The total-return tile shows `formatCurrency(total_return)` as its value with `formatPercent(total_return_pct)` as its hint. Sharpe shows its value or "Not yet available" with a hint when `null`.
- [x] 4.2 Extend `PaperTradingSessionPage.test.tsx` (route the new `/kpis` GET in the mocked client) to assert the tiles render the values (including the total-return amount and percentage), P&L colour follows sign, and the Sharpe tile shows "Not yet available" when `sharpe_ratio` is null. Verify the Vitest passes.

## 5. Verification

- [x] 5.1 Backend gate: `uv run ruff check . && uv run mypy src/cadence && uv run pytest` all pass.
- [x] 5.2 Frontend gate: `npm run typecheck && npx vitest run && npm run build` all pass.
- [x] 5.3 `openspec validate add-session-kpis --strict` passes.
