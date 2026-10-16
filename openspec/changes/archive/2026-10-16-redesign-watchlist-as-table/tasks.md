## 1. Backend — fundamentals on the asset detail read

- [x] 1.1 Add `fundamentals: AssetFundamentalsRead | None = None` to `AssetDetailRead` in `backend/src/cadence/api/schemas.py`; verify with `uv run mypy src/cadence`.
- [x] 1.2 Ensure `get_asset_detail` (`assets/service.py`) makes the `Asset.fundamentals` relationship available (eager-load or access) without triggering a fetch, and map it onto the detail response in the assets router (`api/routers/assets.py`); verify the response carries fundamentals when present and `null` when absent.
- [x] 1.3 Add backend tests in `backend/tests` covering: detail for an asset WITH a fundamentals row includes it; detail for an asset WITHOUT fundamentals returns `null` and still 200; unknown ticker still 404. Verify `uv run pytest -k asset_detail` (or the relevant module) passes.

## 2. Backend — per-asset short-window technical read

- [x] 2.1 Add a single-asset short-window read in `technical_indicators/service.py` that builds the short-window `WatchlistIndicatorSnapshot` for a given asset of ANY membership (reuse the existing row-level short-window + floor + insufficient-history logic; drop the watchlist-membership filter); raise a not-found domain error when the ticker is unknown. Verify with a new service unit test.
- [x] 2.2 Add response schema `AssetIndicatorResponse` (e.g. `{ min_bars: int, indicator: WatchlistIndicatorRead | None }`) in `api/schemas.py`, reusing `WatchlistIndicatorRead`; verify `uv run mypy src/cadence`.
- [x] 2.3 Add route `GET /api/v1/technical-indicators/assets/{ticker}` in `api/routers/technical_indicators.py` (plain read, no cron token), mapping the service result to `AssetIndicatorResponse` and the not-found error to 404. Verify with new API tests: universe asset at/above floor returns short-window values + `min_bars` and NO `gate_pass`/`sma_200`; below-floor asset returns `insufficient_history`; asset with no snapshot returns `indicator: null` (or insufficient) without error; unknown ticker → 404.
- [x] 2.4 Run the backend service + API test modules for technical indicators and verify they pass (`uv run pytest tests/test_technical_indicators_service.py tests/test_technical_indicators_api.py`).

## 3. Backend — verification gates

- [x] 3.1 Run `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` and verify all green.

## 4. Frontend — API/types seams

- [x] 4.1 Add `fundamentals: AssetFundamentals | null` to the `AssetDetail` type in `frontend/src/types/api.ts`; add an `AssetIndicatorResponse` type (`{ min_bars: number; indicator: WatchlistIndicator | null }`). Verify `npm run typecheck` (or `tsc`).
- [x] 4.2 Thread an optional `membership` through `AssetsListParams`, `listAssets`, and `useAssets` in `frontend/src/api/assets.ts` (sent as the `membership` query param when set; omitted otherwise so the Assets page keeps the universe default). Verify an existing/updated `assets` api test asserts the param is sent only when provided.
- [x] 4.3 Add a per-asset technical fetch + hook (`getAssetIndicators(ticker)` + `useAssetIndicators(ticker)`) to `frontend/src/api/technicalIndicators.ts` hitting `GET /api/v1/technical-indicators/assets/{ticker}`, with a query key. Verify with a small api test or via the detail-page test.

## 5. Frontend — extract shared fundamentals + technical rendering

- [x] 5.1 Extract `FundamentalsPanel` (and its helpers) from `WatchlistPage.tsx` into a shared component under `frontend/src/components` (or `pages/assets`), parameterized by an `AssetFundamentals | null`; verify existing fundamentals rendering/tests still pass.
- [x] 5.2 Extract `TechnicalPanel` + `INDICATOR_ROWS` / `REVERSAL_FLAG_ROWS` / `formatCompactNumber` into a shared component that takes `{ indicator, minBars }` and renders values + active reversal chips + "as of" date OR the insufficient-history state; verify its unit test covers the with-history and below-floor states.

## 6. Frontend — asset detail page sections

- [x] 6.1 In `frontend/src/pages/assets/AssetDetailPage.tsx`, render a **Fundamentals** section from `assetDetail.fundamentals` (shared panel; "unavailable" note when `null`) and a **Technical indicators** section from `useAssetIndicators(ticker)` (shared panel; insufficient-history state below floor). A technical/fundamentals load error SHALL surface a message and NOT block the rest of the page. Verify `AssetDetailPage.test.tsx` covers: fundamentals shown when present, unavailable note when absent, technical profile shown at/above floor, insufficient-history state below floor.

## 7. Frontend — watchlist as a table

- [x] 7.1 Rebuild `frontend/src/pages/watchlist/WatchlistPage.tsx` as a table mirroring `AssetsPage`: keep the "Discover emerging companies" `WatchlistRecommendCard` on top, then a `useAssets({ membership: 'watchlist' })`-backed table with debounced search, `SortableHeader` (ticker/name), category/sector `MultiSelectDropdown` filters, watchlist-specific `localStorage` page-size key, and infinite-scroll sentinel. Each row links to `/assets/${ticker}`. Remove the inline fundamentals/technical panels. Verify `WatchlistPage.test.tsx`.
- [x] 7.2 Rewrite `WatchlistPage.test.tsx` for the table: lists watchlist rows (fetched with `membership: 'watchlist'`), search/sort/filter controls present and wired, a row links to the asset detail, the Discover run still triggers, and fundamentals/technical values are NOT rendered inline. Verify the test file passes.
- [x] 7.3 Remove `useWatchlist`/`listWatchlist` from `frontend/src/api/assets.ts` if no other consumer remains (confirm with a repo search); otherwise leave them and note why. Verify typecheck + no unused-symbol lint errors.

## 8. Frontend — verification gates

- [x] 8.1 Run the frontend typecheck, `npm run test` (vitest), and `npm run build`; verify all green.

## 9. Spec validation

- [x] 9.1 Run `openspec validate redesign-watchlist-as-table --strict` and verify it passes.
