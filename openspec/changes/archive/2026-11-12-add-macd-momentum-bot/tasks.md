## 1. Backend

- [x] 1.1 Create `strategy_bots/macd_momentum.py` (`MacdMomentumParams`, EMA replay helper, `MacdMomentumStrategy`) and wire `StrategyKey.MACD_MOMENTUM` ("MACD Momentum"), explanation and registry; verify with pytest (replay matches a hand-computed short series; bullish cross above zero enters; cross below zero holds; no cross holds; holding holds after a cross-down; insufficient history; never short; params validation incl. slow ≤ fast rejected).
- [x] 1.2 Add the `macd_momentum_algo10` preset (default); verify with preset recipe/integrity tests and the catalog listing test.

## 2. Frontend

- [x] 2.1 `BuildBotCard`: MACD inputs (fast / slow / signal) with validation and payload, own setters; verify with vitest (preset fills 12/26/9 and submits them; slow ≤ fast blocks submit).
- [x] 2.2 `macdChart.ts` illustration registered in `strategyCharts.ts`; verify with the registry test.

## 3. Docs

- [x] 3.1 Update `docs/trading-bots-roadmap.md`: MACD shipped (7 of 16).

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate add-macd-momentum-bot --strict` passes.
