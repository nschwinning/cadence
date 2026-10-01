## 1. Backend — config read endpoint

- [x] 1.1 Add `get_indicator_config()` to `technical_indicators/service.py` that assembles the configured setup from `constants.py` — the indicator set (each with key, human-readable label, and its period/lookback params), the trend-gate rules + thresholds (regime: close>SMA200, SMA50>SMA200, SMA200 slope ≥ `SMA_SLOPE_MIN`; momentum: MACD histogram > `MACD_HIST_MIN`, RSI > `RSI_MOMENTUM_MIN`, ROC(120) > `ROC_MOMENTUM_MIN`; rising-OBV soft bonus; missing-required-indicator-fails-gate rule), and the reversal-flag definitions + thresholds (`RSI_OVERBOUGHT`, `SLOPE_FLATTEN_EPS`, MACD rollover, RSI rollover, return deceleration, OBV/price divergence); pure, no DB session. Verify a unit test asserts the returned values equal the current `constants.py` values (periods and thresholds) and that all indicator/flag entries are present.
- [x] 1.2 Add the `TechnicalIndicatorConfig` response schema(s) to `api/schemas.py` modeling the grouped shape from design.md (`indicators[]`, `trend_gate`, `reversal_flags[]` + thresholds); verify `uv run mypy src/cadence` passes and the service result validates against the schema in a unit test.
- [x] 1.3 Add the `GET /api/v1/technical-indicators/config` route to `api/routers/technical_indicators.py` — thin: call `service.get_indicator_config()`, return `model_validate`d; NO cron-token dependency (plain read). Verify an API test returns 200 with the full config and (unlike `POST /runs`) succeeds without an `X-Cron-Token` header.
- [x] 1.4 Run `uv run ruff check . && uv run mypy src/cadence && uv run pytest` and verify the full backend suite is green.

## 2. Frontend — nav tab, API hook, and page

- [x] 2.1 Mirror the config response in `frontend/src/types/api.ts` (a `TechnicalIndicatorConfig` type matching the backend schema) and add `frontend/src/api/technicalIndicators.ts` with a query-key factory, a raw `getTechnicalIndicatorConfig()` calling `apiClient.get('/api/v1/technical-indicators/config')`, and a `useTechnicalIndicatorConfig()` TanStack Query hook (pattern from `api/dashboard.ts`); verify `npm run typecheck` passes.
- [x] 2.2 Add a `TechnicalIndicatorsIcon` under `frontend/src/components/icons/` and a "Technical Indicators" entry to `NAV_ITEMS` in `components/layout/Sidebar.tsx` (to `/technical-indicators`); verify a Vitest test that the nav renders the new entry linking to the route.
- [x] 2.3 Add the `TechnicalIndicatorsPage` under `frontend/src/pages/technical-indicators/` rendering the indicator set, periods, trend-gate rules, and reversal flags in grouped sections from the hook, with loading and error states, and wire the route into `App.tsx` inside the `Layout` route; verify Vitest tests for the grouped-config render (from fixture data), the loading state, and the error state.
- [x] 2.4 Run `npm run typecheck && npx vitest run && npm run build` and verify all pass.

## 3. Validation

- [x] 3.1 Run `openspec validate add-technical-indicators-page --strict` and verify it passes.
