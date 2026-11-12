## 1. Strategy

- [x] 1.1 Create `strategy_bots/atr_band_trend.py` (`AtrBandTrendParams`, close ATR helper, SuperTrend replay, Keltner bands, `AtrBandTrendStrategy`) and wire `StrategyKey.ATR_BAND_TREND`, display name "ATR-Band Trend", explanation and registry entry; verify with pytest (SuperTrend entry in up-trend, no entry in down-trend, HOLD while holding even after a down-turn, ratchet keeps the lower band from falling in an up-trend; Keltner entry above upper, exit below mid, hold with midline exit off; insufficient history HOLD; determinism; params validation incl. extra fields rejected).
- [x] 1.2 Add the `atr_band_supertrend_algo9` (default) and `atr_band_keltner_algo21` presets; verify with the existing preset integrity tests plus an assertion on both presets' values and the catalog endpoint.

## 2. Frontend

- [x] 2.1 `BuildBotCard`: ATR-Band inputs (version, window, multiplier, Keltner midline checkbox), payload and validation, preset prefill; verify with vitest (selecting the Keltner preset fills 20/1/on, payload shape, invalid multiplier blocks submit).
- [x] 2.2 `atrBandChart.ts` illustration registered in `strategyCharts.ts`; verify with the strategy-chart registry test.

## 3. Docs

- [x] 3.1 Update `docs/trading-bots-roadmap.md`: Donchian, Rolling-Average Reversion and ATR-Band Trend shipped; Tier 1 complete; ADX next.

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate add-atr-band-trend-bot --strict` passes.
