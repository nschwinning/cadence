## 1. Backend

- [x] 1.1 Create `strategy_bots/vama.py` (`VamaParams`, volatility / α / replay helpers, `VamaStrategy`) and wire `StrategyKey.VAMA` ("VAMA"), explanation, registry; verify with pytest (fixed α = α_max on moving prices and α_min on flat ones; adaptive α = half α_max at half the average volatility, clamped at α_min; replay matches a hand-computed short series; close above enters; at/below exits; holding above holds; insufficient history; never short; params validation incl. α_min ≥ α_max rejected).
- [x] 1.2 Add the `vama_algo30` preset (default, adaptive off); verify with preset recipe/integrity tests and the catalog listing test.

## 2. Frontend

- [x] 2.1 `BuildBotCard`: VAMA inputs with validation and payload; verify with vitest (preset fills 20 / 0.02 / 0.2 / adaptive off and submits all five; α min ≥ α max blocks submit).
- [x] 2.2 `vamaChart.ts` illustration registered in `strategyCharts.ts`; verify with the registry test.

## 3. Docs

- [x] 3.1 Update `docs/trading-bots-roadmap.md`: VAMA shipped (11 of 16), course adaptation is a no-op, adaptive mode added.

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate add-vama-bot --strict` passes.
