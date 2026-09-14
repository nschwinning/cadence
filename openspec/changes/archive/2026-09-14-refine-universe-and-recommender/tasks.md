## 1. Recommender excludes existing assets

- [x] 1.1 Add an exclusion list to the recommender contract: `RecommenderAgent.recommend` and `.build_prompt` take `exclude_tickers: list[str]`. Update `OpenAIRecommenderAgent` and the stub to accept and honor it (the stub must not return excluded tickers). Verify: signatures updated; `isinstance` seam intact.
- [x] 1.2 `build_recommendation_prompt`: render an explicit "do NOT propose any of these tickers already in the universe: …" section (state "none" when empty); reinforce in the agent instructions that existing tickers are forbidden. Verify: a unit test asserts the exclusion tickers appear in the built prompt.
- [x] 1.3 `service.execute_run`: gather the current universe's tickers via `assets_service.list_assets(session)` and pass them to `build_prompt` and `recommend`. Keep the server-side dedup as a safety net. Verify: a service test with a seeded universe asserts existing tickers are passed as exclusions and are not re-added.

## 2. Restrict supported categories to stock + crypto

- [x] 2.1 Add `SUPPORTED_CATEGORIES = frozenset({AssetCategory.STOCK, AssetCategory.CRYPTO})` (in `assets/category.py`). Add `UnsupportedCategoryError` to `assets/errors.py`. Verify: imports cleanly.
- [x] 2.2 `assets/service.add_asset`: after classifying the fetched asset, if its category is not in `SUPPORTED_CATEGORIES`, raise `UnsupportedCategoryError` naming the category (do NOT persist it). Keep the enum members (STOCK/CRYPTO/ETF/FUND/OTHER) so classification can detect and reject, and so any existing rows still read. Verify: adding a ticker the fake provider classifies as ETF/FUND is rejected; stock and crypto still add.
- [x] 2.3 `api/routers/assets.py`: map `UnsupportedCategoryError` to HTTP 422 with the reason. Verify: pytest asserts a 422 for an unsupported category.
- [x] 2.4 `recommendations/service.create_run`: reject a run whose requested categories include anything outside stock/crypto (raise `RecommendationValidationError`). Verify: pytest asserts the rejection.

## 3. Frontend

- [x] 3.1 Limit category choices to stock + crypto wherever a category is selected or filtered — the recommendation-run form and the Assets list category filter. Keep the category badge covering both. Verify: `npm run typecheck`, `npm run test`, `npm run build` pass; a test asserts only stock/crypto are offered.

## 4. Verification

- [x] 4.1 Backend: `uv run pytest` green (279), `uv run ruff check .` clean, `uv run mypy src/cadence` clean, `uv run alembic check` no new operations.
- [x] 4.2 `openspec validate refine-universe-and-recommender --strict` passes.
