## 1. Strategy

- [x] 1.1 Create `strategy_bots/bayesian_trend.py` (`BayesianTrendParams`, `BayesianTrendStrategy`, `posterior` helper in log space); wire `StrategyKey.BAYESIAN_TREND` ("Bayesian Trend Predictor"), explanation, registry; verify with pytest (single-update posterior matches the course formula; steady up returns → enter; flat returns → hold; holding through FLAT → hold; down regime while holding → exit; down regime while flat → hold; below-threshold MAP → hold; extreme return keeps direction; insufficient history; never short; params validation).
- [x] 1.2 Add the `bayesian_trend_algo33` preset (default); verify with preset recipe/integrity tests and the catalog listing test.

## 2. Frontend

- [x] 2.1 `BuildBotCard`: Bayesian fields (drift / σs in percent), validation and payload; verify with vitest (preset fills and submits the params as fractions; threshold ≤ 1/3 blocks submit).
- [x] 2.2 `bayesianChart.ts` registered in `strategyCharts.ts`; verify with the registry test.

## 3. Docs

- [x] 3.1 Update `docs/trading-bots-roadmap.md`: Bayesian Trend Predictor shipped; roadmap complete.

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate add-bayesian-trend-bot --strict` passes.
