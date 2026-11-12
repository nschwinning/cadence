## 1. Backend

- [x] 1.1 Create `strategy_bots/adx_trend.py` (directional-movement helpers, `AdxTrendParams`, `AdxTrendStrategy`) and wire `StrategyKey.ADX_TREND` ("ADX Trend Strength"), explanation, registry; verify with pytest (helpers on a hand-computed series; strong up-trend entry; strong down-trend and weak trend hold; exit below threshold; insufficient history; never short; params validation).
- [x] 1.2 Add the ADX danger exit to `RollingAverageReversionParams` / strategy (fields, required history, exit check first in both modes); verify with pytest (exit on losing trade in strong downtrend; no exit in profit; no exit when −DI ≤ +DI or DX ≤ threshold; filter off = unchanged signals on existing test series).
- [x] 1.3 Add `adx_trend_algo12` (default) and `rolling_reversion_vwap_adx_algo15` presets; verify with preset integrity/recipe tests and the catalog listing test.

## 2. Frontend

- [x] 2.1 `BuildBotCard`: ADX inputs (period, threshold) with validation and payload; reversion "ADX danger exit" checkbox + lookback/threshold sent only when on; preset prefill; verify with vitest (ADX preset fills 10/20; Algo 15 preset ticks the filter and submits its fields; Algo 5 payload unchanged).
- [x] 2.2 `adxChart.ts` illustration registered in `strategyCharts.ts`; verify with the registry test.

## 3. Docs

- [x] 3.1 Update `docs/trading-bots-roadmap.md`: ADX shipped, Algo 15 preset added, next Tier 2 bot named.

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate add-adx-trend-bot --strict` passes.
