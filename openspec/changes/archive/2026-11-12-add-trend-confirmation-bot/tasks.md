## 1. Shared indicator maths

- [x] 1.1 Create `technical_indicators/series.py` (sma, macd_histogram, wilder, rsi, roc, obv, obv_change) and make `compute_snapshot` use it; verify with a golden-value parity test on fixed fixtures (captured before the refactor) plus the existing technical-indicator tests unchanged.

## 2. Strategy

- [x] 2.1 Create `strategy_bots/trend_confirmation.py` (`TrendConfirmationParams`, `TrendConfirmationStrategy`) on the shared series; wire `StrategyKey.TREND_CONFIRMATION` ("Trend Confirmation"), explanation, registry; verify with pytest (all legs → enter; RSI at/above cap → hold; MACD hist negative while holding → exit; RSI 47 while holding → hold; RSI above cap while holding → hold; ROC leg enabled & negative → hold flat / exit holding; OBV leg likewise; undefined value → hold; insufficient history; never short; params validation).
- [x] 2.2 Add the `trend_confirmation_cadence` preset (default); verify with preset recipe/integrity tests and the catalog listing test.

## 3. Frontend

- [x] 3.1 `BuildBotCard`: trend-confirmation fields (grouped; ROC/OBV toggles reveal their windows), validation and payload; verify with vitest (preset fills all values and submits the full params; rsi_exit > rsi_entry blocks submit; enabling ROC sends `use_roc: true`).
- [x] 3.2 `trendConfirmationChart.ts` registered in `strategyCharts.ts`; verify with the registry test.

## 4. Docs

- [x] 4.1 Update `docs/trading-bots-roadmap.md`: Trend Confirmation shipped (14 of 16); Tier 2 complete; indicator maths shared.

## 5. Verification

- [x] 5.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 5.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 5.3 `openspec validate add-trend-confirmation-bot --strict` passes.
