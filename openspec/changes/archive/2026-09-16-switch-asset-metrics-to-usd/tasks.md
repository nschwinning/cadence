## 1. Backend — FX normalization target + metrics

- [x] 1.1 In `assets/market_data.py`, change `fetch_fx_rate` to return a `currency → USD` rate: `1.0` when `currency == "USD"`, otherwise the yfinance pair `f"{currency}USD=X"`. Update its docstring/return description EUR→USD. Verify with a provider unit test (USD → 1.0; a non-USD currency uses the `…USD=X` pair).
- [x] 1.2 In `assets/metrics.py`, rename the derived fields `price_eur/market_cap_eur/avg_daily_turnover_eur → *_usd`, update the module/docstring wording EUR→USD, and pass the USD rate through the unchanged `_convert`. Verify the metrics unit test asserts USD-normalized outputs.

## 2. Backend — thresholds + evaluator

- [x] 2.1 In `assets/constants.py`, rename `MIN_PRICE_EUR`, `MIN_AVG_DAILY_TURNOVER_EUR`, `MIN_MARKET_CAP_EUR`, `MIN_CRYPTO_AVG_DAILY_TURNOVER_EUR`, `MIN_CRYPTO_MARKET_CAP_EUR` to their `*_USD` names, keeping the same numeric values, and change the module docstring "expressed in EUR" → "expressed in USD".
- [x] 2.2 In `assets/evaluation.py`, rename `AssetMetrics` fields to `price_usd/avg_daily_turnover_usd/market_cap_usd`, update the imported constants and `_CriterionSpec` metric accessors, and reword the docstring EUR→USD. Leave the criterion `name` values (`price`, `market_cap`, …) unchanged. Verify the evaluation tests pass against the `*_usd` fields/constants.

## 3. Backend — schema + migration + API

- [x] 3.1 In `assets/models.py`, rename the mapped columns `market_cap_eur → market_cap_usd` and `avg_daily_turnover_eur → avg_daily_turnover_usd`.
- [x] 3.2 Add an Alembic migration `add_usd_metric_columns_to_assets` with `down_revision = "d3f8b6a2c9e1"`: `upgrade` renames `assets.market_cap_eur → market_cap_usd` and `assets.avg_daily_turnover_eur → avg_daily_turnover_usd` via `op.alter_column(..., new_column_name=...)`; `downgrade` reverses both. No data backfill. Verify `uv run alembic upgrade head`, then `downgrade -1`, then `upgrade head` round-trip, and `uv run alembic check` reports no drift.
- [x] 3.3 In `api/schemas.py`, rename the `AssetRead` fields `market_cap_eur → market_cap_usd` and `avg_daily_turnover_eur → avg_daily_turnover_usd`. Verify an API/serialization test exposes the `*_usd` fields.

## 4. Frontend — USD asset metrics

- [x] 4.1 In `types/api.ts`, rename the `Asset` fields `market_cap_eur → market_cap_usd` and `avg_daily_turnover_eur → avg_daily_turnover_usd`. Verify `npm run typecheck` passes.
- [x] 4.2 In `pages/assets/AssetsPage.tsx`, replace the compact `€` formatter with a `$` compact formatter (B/M/K), retitle the columns `Market Cap ($)` and `Avg Daily Turnover ($)`, read the renamed `*_usd` fields, and render the eligibility-criteria thresholds with the `$` formatter. Update `AssetsPage.test.tsx` `€…` assertions to `$…`. Verify `npx vitest run` passes.

## 5. Verification

- [x] 5.1 Repo-wide sweep: no stray `_eur`, `EUR`, or `€` remain in `backend/src`, `frontend/src`, or their tests except where genuinely unrelated (grep and confirm).
- [x] 5.2 Backend gate: `uv run ruff check . && uv run mypy src/cadence && uv run pytest` all pass.
- [x] 5.3 Frontend gate: `npm run typecheck && npx vitest run && npm run build` all pass.
- [x] 5.4 `openspec validate switch-asset-metrics-to-usd --strict` passes.
