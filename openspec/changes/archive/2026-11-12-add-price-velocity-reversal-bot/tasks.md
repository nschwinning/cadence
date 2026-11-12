## 1. Backend

- [x] 1.1 Create `strategy_bots/price_velocity_reversal.py` (`PriceVelocityReversalParams`, `PriceVelocityReversalStrategy`) and wire `StrategyKey.PRICE_VELOCITY_REVERSAL` ("Price Velocity Reversal"), explanation, registry; verify with pytest (decelerating sharp drop enters; accelerating drop holds; small drop holds; velocity flip exits; flat/down bar while holding holds; insufficient history; threshold is price-independent — same signal at $10 and $1,000; never short; params validation).
- [x] 1.2 Add the `price_velocity_algo48` preset (default); verify with preset recipe/integrity tests and the catalog listing test.

## 2. Frontend

- [x] 2.1 `BuildBotCard`: threshold input (percent in, fraction out) with validation; verify with vitest (preset fills 0.2 and submits 0.002; threshold ≤ 0 blocks submit).
- [x] 2.2 `velocityChart.ts` illustration registered in `strategyCharts.ts`; verify with the registry test.

## 3. Docs

- [x] 3.1 Update `docs/trading-bots-roadmap.md`: Price Velocity Reversal shipped (12 of 16), percent threshold.

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate add-price-velocity-reversal-bot --strict` passes.
