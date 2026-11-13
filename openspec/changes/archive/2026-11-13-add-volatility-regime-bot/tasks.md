## 1. Strategy

- [x] 1.1 Create `strategy_bots/volatility_regime.py` (`VolatilityRegimeParams`, `VolatilityRegimeStrategy`, rolling-ATR / regime helpers); wire `StrategyKey.VOLATILITY_REGIME` ("Volatility Regime Switcher"), explanation, registry; verify with pytest (calm → enter above HL2 / exit below HL2 / hold at HL2; volatile → enter below SMA × (1 − dev) / hold above SMA / exit at SMA; deviation blocks a shallow dip; ATR equal to baseline is trend; insufficient history; never short; params validation; required history).
- [x] 1.2 Add the `volatility_regime_algo20` preset (default); verify with preset recipe/integrity tests and the catalog listing test.

## 2. Frontend

- [x] 2.1 `BuildBotCard`: Volatility Regime fields (deviation in percent), validation and payload; verify with vitest (preset fills values and submits the full params with the deviation as a fraction; an invalid baseline blocks submit).
- [x] 2.2 `volatilityRegimeChart.ts` registered in `strategyCharts.ts`; verify with the registry test.

## 3. Docs

- [x] 3.1 Update `docs/trading-bots-roadmap.md`: Volatility Regime Switcher shipped; baseline and regime-mapping notes.

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate add-volatility-regime-bot --strict` passes.
