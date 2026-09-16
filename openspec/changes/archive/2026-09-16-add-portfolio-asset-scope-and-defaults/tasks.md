## 1. Backend — asset scope model + default capital

- [x] 1.1 Add an `AssetScope` `StrEnum` (`stocks`, `crypto`, `both`) and a pure `scope_categories(scope) -> frozenset[AssetCategory]` helper in `assets/category.py`. Verify with a unit test (each scope → expected category set; invalid value rejected).
- [x] 1.2 Change the default allocated capital from `100000.0` to `10000.0` in `AIPortfolioBuildRequest` (`api/schemas.py`) and in `AIBuildParams` (constructor default + `from_payload` fallback, `ai_portfolio/service.py`). Keep the `ge=1000` minimum.
- [x] 1.3 Add `asset_types: str = "both"` to `AIPortfolioBuildRequest` (validated against `AssetScope`; invalid → 422) and to `AIBuildParams` (round-tripped in `to_payload`/`from_payload`, legacy payloads default to `both`). Verify the schema validates good values and rejects a bad one.

## 2. Backend — scope enforcement in build + rebalance

- [x] 2.1 Persist the selected `asset_types` into the session's `session_metadata` at build time (next to `risk_profile`), and filter the build candidate universe via `list_assets(session, categories=scope_categories(scope))`. Verify a stocks-only build only offers stock candidates.
- [x] 2.2 In the rebalance path, read the scope from `session_metadata` (default `both` when absent) and filter the rebalance candidate universe the same way. Verify a crypto-only session's rebalance only offers crypto candidates, and a legacy session (no `asset_types`) is treated as `both`.
- [x] 2.3 Add an optional `allowed_categories: Collection[AssetCategory] | None = None` parameter to `add_asset` (`assets/service.py`) that rejects a derived category outside the set via `UnsupportedCategoryError`; thread the session scope through `_add_discovered_assets` (both build and rebalance call sites) so out-of-scope discovered assets are rejected. Verify manual add/recommender are unchanged (default `None`) and a crypto-only discovery of a stock is rejected.
- [x] 2.4 Bug fix — apply the session's risk profile at rebalance: thread `risk_profile: str` through the rebalance agent surface (`AIPortfolioAgent.rebalance` Protocol, `OpenAIAIPortfolioAgent.rebalance`, `rebalance_ai_portfolio`, `_run_rebalance`, and `_build_rebalance_input` prompt) in `ai_portfolio/agent.py`, and in the rebalance service read `session_row.session_metadata.get("risk_profile", "balanced")` and pass it to `agent.rebalance`. Update the fake agent in tests to the new signature. Verify a session built with a non-default risk profile rebalances with that profile (and a legacy session with no persisted profile defaults to `balanced`).

## 3. Frontend — build form + request

- [x] 3.1 Add `asset_types?: 'stocks' | 'crypto' | 'both'` to `AIPortfolioBuildRequest` in `types/api.ts` (update the doc comment for the new capital default). Verify `npm run typecheck` passes.
- [x] 3.2 In `BuildAIPortfolioCard.tsx`, default the capital input to `10000`, add an asset-scope control (Both / Stocks only / Crypto only, default Both), and include `asset_types` in the mutate payload. Verify with a component test asserting the default capital, the default scope, and that a chosen scope is sent.

## 4. Frontend — USD currency

- [x] 4.1 Switch the shared `currencyFormatter` in `lib/format.ts` from EUR to USD (`$`); update `format.test.ts` expectations to `$…`. Verify the Vitest passes.
- [x] 4.2 Replace the remaining per-file EUR `Intl.NumberFormat` instances (notably `PaperTradingSessionPage.tsx`'s `eur`) with the shared `formatCurrency`, and update any tests asserting `€…` to `$…`. Verify `npx vitest run` passes.

## 5. Verification

- [x] 5.1 Backend gate: `uv run ruff check . && uv run mypy src/cadence && uv run pytest` all pass.
- [x] 5.2 Frontend gate: `npm run typecheck && npx vitest run && npm run build` all pass.
- [x] 5.3 `openspec validate add-portfolio-asset-scope-and-defaults --strict` passes.
