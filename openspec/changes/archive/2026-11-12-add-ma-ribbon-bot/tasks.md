## 1. Backend

- [x] 1.1 Create `strategy_bots/ma_ribbon.py` (`MaRibbonParams`, `MaRibbonStrategy`) and wire `StrategyKey.MA_RIBBON` ("MA Ribbon"), explanation, registry; verify with pytest (aligned rise enters; partial alignment holds; falling holds flat; holding holds after a down-turn; insufficient history; never short; params must strictly increase).
- [x] 1.2 Add the `ma_ribbon_algo18` preset (default); verify with preset recipe/integrity tests and the catalog listing test.

## 2. Frontend

- [x] 2.1 `BuildBotCard`: ribbon inputs (fast / mid / slow) with own setters, validation and payload; verify with vitest (preset fills 5/10/20 and submits; mid ≤ fast blocks submit).
- [x] 2.2 `maRibbonChart.ts` illustration registered in `strategyCharts.ts`; verify with the registry test.

## 3. Docs

- [x] 3.1 Update `docs/trading-bots-roadmap.md`: MA Ribbon shipped (10 of 16).

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate add-ma-ribbon-bot --strict` passes.
