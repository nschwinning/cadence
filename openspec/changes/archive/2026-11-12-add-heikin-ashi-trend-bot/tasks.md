## 1. Backend

- [x] 1.1 Create `strategy_bots/heikin_ashi_trend.py` (`HeikinAshiTrendParams`, HA replay helper, `HeikinAshiTrendStrategy`) and wire `StrategyKey.HEIKIN_ASHI_TREND` ("Heikin-Ashi Trend"), explanation and registry; verify with pytest (HA candles match a hand-computed series; green enters; red holds flat / exits holding; filter: green without strong volume holds, with strong volume enters, fading volume exits, zero-volume window never strong; required history per mode; never short; params validation).
- [x] 1.2 Add `heikin_ashi_algo11` (default) and `heikin_ashi_volume_algo37` presets; verify with preset recipe/integrity tests and the catalog listing test.

## 2. Frontend

- [x] 2.1 `BuildBotCard`: Heikin-Ashi branch (volume filter checkbox + window), payload with `volume_window` only when on, preset prefill; verify with vitest (Algo 11 preset submits `{volume_filter: false}`; Algo 37 preset ticks the filter and submits window 20; window < 2 blocks submit).
- [x] 2.2 `heikinAshiChart.ts` illustration registered in `strategyCharts.ts`; verify with the registry test.

## 3. Docs

- [x] 3.1 Update `docs/trading-bots-roadmap.md`: Heikin-Ashi shipped (8 of 16).

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate add-heikin-ashi-trend-bot --strict` passes.
