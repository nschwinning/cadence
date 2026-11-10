## 1. Strategy (backend)

- [x] 1.1 Create `strategy_bots/rolling_average_reversion.py` with `RollingAverageReversionParams` (fields, defaults, bounds and revert-mode ordering validator per design decisions 1 and 3; `required_history = window`) and the pure `RollingAverageReversionStrategy` (sma / typical / vwap average over `bars[-window:]`, band deviation and population-std z-score, one-sided revert exit, bracket hold, HOLD on zero volume / zero std / short history). Verify: new `tests/test_strategy_bots_rolling_reversion.py` covers band entry, in-band hold, bare-cross entry, z-score entry, revert exit incl. overshoot above the average, revert hold below the exit level, bracket hold while holding, the three average types on the same bars, vwap zero-volume hold, zscore zero-std hold, no short above the average, insufficient history, and each invalid-params case.
- [x] 1.2 Add `StrategyKey.ROLLING_AVERAGE_REVERSION = "rolling_average_reversion"`, its display name ("Rolling-Average Reversion") and plain-language explanation in `constants.py`, and register it in `registry.py`. Verify: an API test asserts the strategy catalog includes it with display name, explanation, required history 20, and a params schema.

## 2. Presets (backend)

- [x] 2.1 Add the four presets to `presets.py` (`rolling_reversion_sma_band_algo5` default, `rolling_reversion_zscore_algo4`, `rolling_reversion_mean_cross_algo14`, `rolling_reversion_vwap_cross_algo39`), each with the full eight-field params dict and its course risk values. Verify: extend the parametrized course-recipe test in `tests/test_strategy_bots_presets.py` with the four rows; the existing integrity tests (valid params, one default per strategy, unique keys) still pass; the API preset-list order test is updated for the new entries.
- [x] 2.2 Verify end to end that a session can be created from a Rolling-Average Reversion preset. Verify: a service test creates a session from `rolling_reversion_vwap_cross_algo39` with no overrides and asserts the strategy key, params, TP 0.5% / SL 1% / drawdown 5%, and not customized.

## 3. Frontend form

- [x] 3.1 Add Rolling-Average Reversion state and fields to `BuildBotCard.tsx`: average type, window, distance, band entry/exit as percents or z entry/exit, exit mode; per-strategy validation (window ≥ 2, non-negative thresholds, revert-mode ordering); a params payload that always sends all eight fields (band thresholds as fractions); and a strategy-aware preset→form mapping that converts band fractions to percent strings. Verify: vitest — selecting the strategy applies the Algo 5 preset (SMA / 20 / band / 1% / 0.5% / revert, SL 2%, TP off); switching distance to z-score shows the σ fields; the submit payload carries all eight params with fractions; revert mode with exit ≥ entry blocks submit.
- [x] 3.2 Add the general preset selector (shown when the selected strategy has more than one preset; value = applied preset; choosing applies it) alongside the existing Customized marker and Reset button; keep the Donchian version selector in sync. Verify: vitest — the selector lists the four reversion presets and choosing "VWAP Cross Reversion (Algo 39)" applies vwap / 60 / bare cross / bracket with TP 0.5% / SL 1%; Donchian shows a selector with both presets, and choosing Algo 8 switches the version to Locked; MA Crossover (single preset) shows no selector; existing BuildBotCard tests updated with the new presets in the mock and still pass.

## 4. Strategy guide chart

- [x] 4.1 Add `rollingReversionChart.ts` (synthetic price, rolling mean, lower band, entry and exit markers) and register it in `strategyCharts.ts` with an aria-label. Verify: `strategyCharts.test.ts` asserts the new key resolves to a descriptor whose option has the price, mean and band series plus entry/exit markers.

## 5. Verification gates

- [x] 5.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` against the 5435 Postgres test DB. Verify: all green; then tear the Cadence DB container down.
- [x] 5.2 Frontend: `cd frontend && npx vitest run && npx tsc -p tsconfig.app.json --noEmit`. Verify: vitest green; the type-check reports no errors beyond the three known pre-existing axios-mock errors in `BotSessionPage.test.tsx` and `BotValueChart.test.tsx`.
- [x] 5.3 `openspec validate add-rolling-average-reversion-bot --strict`. Verify: passes.
