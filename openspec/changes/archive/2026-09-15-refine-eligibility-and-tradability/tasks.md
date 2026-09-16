> Retroactive change: the code below already exists in the working tree. Tasks
> are checked off as verification of the merged behavior, not net-new work.

## 1. Category-specific eligibility criteria

- [x] 1.1 `assets/constants.py`: add crypto thresholds `MIN_CRYPTO_AVG_DAILY_TURNOVER_EUR` (10_000_000), `MIN_CRYPTO_MARKET_CAP_EUR` (2_000_000_000), `MIN_CRYPTO_HISTORY_YEARS` (1), documenting why crypto drops the price criterion. Verify: imports cleanly.
- [x] 1.2 `assets/evaluation.py`: model per-category criteria profiles (a `_CriterionSpec` of name + metric accessor + threshold + comparator). Equity profile keeps all four criteria; crypto profile omits price and uses the crypto thresholds. `evaluate(metrics, category=AssetCategory.STOCK)` selects the profile; unknown categories fall back to equities. Verify: unit tests cover both profiles.
- [x] 1.3 `assets/service.add_asset`: pass `derived.category` into `evaluate`. Verify: crypto adds are scored without a price criterion.
- [x] 1.4 Frontend `AssetsPage.tsx`: derive failed-criterion labels from each criterion's actual `threshold` (not hardcoded strings) so labels are correct across categories. Verify: a test asserts the tooltip renders per-category thresholds for a stock vs a crypto asset.

## 2. Authoritative brokerage tradability + stored canonical symbol

- [x] 2.1 `broker/models.py` + `broker/base.py`: add `BrokerAsset` and `Broker.get_asset(symbol, asset_class)`; implement in `broker/alpaca.py` (GET /v2/assets, URL-encode crypto slash, 404 → None) and `broker/stub.py` (tradable, None for a dotted equity). Verify: broker unit tests.
- [x] 2.2 `assets/models.py` + migration `c4e7a1f9b2d3`: add nullable `alpaca_symbol` column + index. Verify: `alembic upgrade head`/`downgrade` round-trip clean; `alembic check` no drift; single head.
- [x] 2.3 `assets/service.add_asset(session, ticker, provider, broker)`: after the category gate, look the asset up on the brokerage; raise `UntradeableTickerError` if missing/not tradable; persist `alpaca_symbol` on success. Remove the old dot-heuristic. Verify: service tests for stored symbol, rejection, and connection-error propagation.
- [x] 2.4 `api/routers/assets.py` + `api/app.py`: map `UntradeableTickerError` → 422 and a brokerage `ConnectionError` → 503. Verify: API tests for both.
- [x] 2.5 Thread `broker` through the recommender and AI-portfolio add paths (`recommendations/service.py`, `recommendations/background.py`, `ai_portfolio/service.py`) and expose `alpaca_symbol` in `api/schemas.py` + frontend `types/api.ts`. Verify: those suites pass.

## 3. Verification

- [x] 3.1 Backend: `uv run pytest` green (306), `uv run ruff check .` clean, `uv run mypy src/cadence` clean.
- [x] 3.2 Frontend: `npm run typecheck`, `npx vitest run` (33), `npm run build` all pass.
- [x] 3.3 `openspec validate refine-eligibility-and-tradability --strict` passes.
