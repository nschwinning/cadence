## Context

AI builds/rebalances allocate over the whole supported universe. Build params (`allocated_capital`, `risk_profile`, `daily_rebalancing`) are modelled by `AIBuildParams` (`ai_portfolio/service.py`), stored on the build event's `request_payload`, and mirrored into the session's `session_metadata` JSONB. The universe is fetched with `assets_service.list_assets(session)` (no category filter) at both build (`service.py:256`) and rebalance (`service.py:420`). `list_assets` already supports a `categories` argument. Discovered tickers go through `_add_discovered_assets` → `assets_service.add_asset`, which enforces `SUPPORTED_CATEGORIES` and raises `UnsupportedCategoryError` for anything else. Categories are `AssetCategory.STOCK = "stock"` and `AssetCategory.CRYPTO = "crypto"`. Money is formatted EUR via the shared `formatCurrency` (`lib/format.ts`) plus a few per-file `Intl.NumberFormat` instances (e.g. `PaperTradingSessionPage.tsx`'s `eur`).

The build form (`pages/portfolios/BuildAIPortfolioCard.tsx`) posts `{allocated_capital, risk_profile, daily_rebalancing}`; the API schema `AIPortfolioBuildRequest` defaults capital to `100000.0` (`ge=1000`).

## Goals / Non-Goals

**Goals:**
- Default build capital `10000` (schema + build-param + form).
- A per-portfolio asset scope (stocks/crypto/both, default both) chosen at build time, persisted, and honoured on every rebalance.
- Hard enforcement: the AI only sees in-scope candidates, and out-of-scope discovered assets are rejected before add/trade.
- Display all money in USD (`$`).

**Non-Goals:**
- No DB migration (scope rides `session_metadata`, like `risk_profile`).
- No change to market-hours logic — crypto-only/stocks-only fall out naturally from the existing class-based executor guard (a scoped portfolio only holds one class, and the current `_involves_crypto` / `market_open` logic already handles when to trade).
- No portfolio-level scope editing after build (scope is set at build time).

## Decisions

- **Scope model.** Add a small `StrEnum` `AssetScope` with values `stocks`, `crypto`, `both`, plus a pure helper `scope_categories(scope) -> frozenset[AssetCategory]` (`stocks→{STOCK}`, `crypto→{CRYPTO}`, `both→{STOCK, CRYPTO}`). Place it alongside the category definitions (`assets/category.py`) so both assets and ai_portfolio can import it without a cycle.
- **Request + params.** `AIPortfolioBuildRequest` gains `asset_types: str = Field(default="both")` (validated against `AssetScope`; invalid → 422). `AIBuildParams` gains `asset_types: str = "both"` with `to_payload`/`from_payload` round-tripping it (legacy payloads without the key default to `both`). Default capital becomes `10000.0` in both the schema and `AIBuildParams` (constructor + `from_payload` fallback).
- **Persistence.** Write `asset_types` into `session_metadata` next to `risk_profile` at build (`service.py` ~294). Rebalance reads `session_row.session_metadata.get("asset_types", "both")` and applies the same filter — this closes the loop the `risk_profile` field left open, for this field only.
- **Universe filtering.** At build and rebalance, call `list_assets(session, categories=scope_categories(scope))` instead of the unfiltered call. `both` passes `{STOCK, CRYPTO}` (equivalent to today).
- **Discovery hard-filter.** Give `add_asset` an optional `allowed_categories: Collection[AssetCategory] | None = None` param: when provided, after the category is derived, an asset whose category is not in the set raises `UnsupportedCategoryError` (reused; message notes the scope). `_add_discovered_assets` gains a `scope` and passes `allowed_categories=scope_categories(scope)`. The manual-add router and recommender keep the default `None` (full `SUPPORTED_CATEGORIES` behaviour) — no behaviour change there. Optionally, the agent prompt is told the scope so it does not waste web searches on out-of-scope names (nice-to-have, prompt-only).
- **USD display.** Switch the shared `currencyFormatter` in `lib/format.ts` from `currency: 'EUR'` to `'USD'` (renders `$1,234.50`), and replace the remaining per-file EUR `Intl.NumberFormat` instances (notably `PaperTradingSessionPage.tsx`'s `eur`) with the shared `formatCurrency`. Update any tests asserting `€…` to `$…`.
- **Frontend form.** Capital `useState('10000')`; add an asset-scope control (a `<select>` or radio group: "Both", "Stocks only", "Crypto only" → `both|stocks|crypto`, default `both`); include `asset_types` in the mutate payload. Extend `AIPortfolioBuildRequest` (`types/api.ts`) with `asset_types?: 'stocks' | 'crypto' | 'both'`.
- **Risk profile at rebalance (bug fix).** `risk_profile` is persisted into `session_metadata` at build but never consumed at rebalance: `agent.rebalance` takes no `risk_profile`, so every rebalance runs as the agent's implicit default ("balanced"). Fix by threading `risk_profile: str` through the rebalance agent surface — `AIPortfolioAgent.rebalance` Protocol, `OpenAIAIPortfolioAgent.rebalance`, `rebalance_ai_portfolio`, `_run_rebalance`, and `_build_rebalance_input` (the prompt now states the target risk profile, mirroring the build prompt) — and by having the rebalance service read `session_row.session_metadata.get("risk_profile", "balanced")` and pass it to `agent.rebalance`. Legacy sessions without the key default to `balanced` (unchanged behaviour). This is the same read-from-`session_metadata` pattern used for `asset_types`, applied to the field that was already being written there.

## Risks / Trade-offs

- **Empty scoped universe.** If a user picks crypto-only but the universe has no crypto assets, the build behaves like today's empty-universe case for that scope — the AI has no in-scope candidates and relies on discovery. Acceptable; discovery can still add in-scope names. The existing empty-universe rejection is keyed on the whole universe, so a scoped-empty build is not rejected up front — the AI simply may produce little. Documented, not gated.
- **Legacy sessions.** Sessions built before this change have no `asset_types` in `session_metadata`; rebalance defaults them to `both`, preserving current behaviour. No backfill needed.
- **USD switch is app-wide and user-visible.** It touches every money figure. Mitigated by centralising on `formatCurrency` and updating tests; the underlying stored numbers are unchanged (no data migration, purely presentational).
- **`add_asset` signature change.** Adding an optional keyword keeps all existing callers working; only the AI-discovery path passes the new argument.
