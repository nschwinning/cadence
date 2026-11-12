## 1. Backend

- [x] 1.1 Create `strategy_bots/hma_trend.py` (`HmaTrendParams`, WMA / proper HMA helpers, `HmaTrendStrategy`) and wire `StrategyKey.HMA_TREND` ("HMA Trend"), explanation, registry; verify with pytest (WMA weights; HMA on a linear series equals the latest value; HMA differs from the course-literal raw value on a curved series; rising-above enters; above-but-falling holds; reversal exits; below-but-rising holds; insufficient history; never short; params validation).
- [x] 1.2 Add the `hma_trend_algo19` preset (default); verify with preset recipe/integrity tests and the catalog listing test.

## 2. Frontend

- [x] 2.1 `BuildBotCard`: HMA inputs (fast / slow) with own setters, validation and payload; verify with vitest (preset fills 9/21 and submits; slow ≤ fast blocks submit).
- [x] 2.2 `hmaChart.ts` illustration registered in `strategyCharts.ts`; verify with the registry test.

## 3. Docs

- [x] 3.1 Update `docs/trading-bots-roadmap.md`: HMA shipped (9 of 16), Algo 26 identical to 19, proper HMA used.

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate add-hma-trend-bot --strict` passes.
