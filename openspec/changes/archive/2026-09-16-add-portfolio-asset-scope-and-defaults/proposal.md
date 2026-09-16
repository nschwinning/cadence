## Why

Today an AI-managed portfolio is always built over the **entire** supported universe (stocks + crypto), and the build form defaults to a large, arbitrary €100,000 figure. Users want to (a) start from a sensible default of **$10,000** and (b) decide up front whether a portfolio should hold **stocks only, crypto only, or both** — a constraint that must stick across daily rebalances. The money figures also currently render in **EUR (€)** even though Alpaca settles in **USD**, which is misleading.

## What Changes

- **Default build capital is now `10000`** (was `100000`) in the API request schema, the build-param defaults, and the frontend build form. The existing `ge=1000` minimum is unchanged.
- **New per-portfolio asset-scope selection** on the AI build request: `asset_types` ∈ {`stocks`, `crypto`, `both`}, default `both` (preserves current behaviour). The selection is persisted in `session_metadata` (the same path as `risk_profile`), so daily rebalances honour it — **no DB migration**.
- **Build and rebalance filter the candidate universe** by the selected categories (`list_assets(..., categories=...)`), and **AI-discovered new assets are hard-filtered**: a discovered asset whose category falls outside the selection is rejected before it is added or traded.
- **Money is displayed in USD (`$`)** across the app: the shared `formatCurrency` helper and the remaining per-file EUR formatters switch to USD.
- Crypto-only vs stocks-only interacts correctly with the existing market-hours logic (crypto trades around the clock; equities skip when the market is closed) — the current class-based logic already covers this once the universe is scoped.
- **Bug fix:** the session's `risk_profile` is now re-read from `session_metadata` at rebalance time and passed to the AI rebalance agent. Today it is persisted at build but never consumed by rebalance, so an "aggressive" or "conservative" session silently rebalances as "balanced".

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `ai-paper-trading`: the "Build an AI portfolio and execute it as paper trades" requirement gains an asset-scope input (stocks/crypto/both) and a new `$10,000` default capital; the build restricts its candidate universe to the selected categories, persists the scope on the session, and hard-filters AI-discovered assets to that scope.
- `daily-rebalancing`: the "Rebalance a session" requirement restricts the rebalance candidate universe to the session's persisted asset scope and hard-filters AI-discovered assets to that scope, so the stocks/crypto/both choice is honoured on every automated rebalance; it also re-reads the session's persisted risk profile and applies it to the rebalance (fixing a gap where risk profile was ignored at rebalance).
- `app-shell`: the AI build form gains an asset-type selector and defaults capital to `10000`; all monetary values render in USD (`$`).

## Impact

- **Backend**: `api/schemas.py` (`AIPortfolioBuildRequest` default + new `asset_types`), `ai_portfolio/service.py` (`AIBuildParams`, build/rebalance universe filtering, `_add_discovered_assets` scope enforcement, `session_metadata` write/read), `assets/service.py` (`add_asset` optional allowed-categories guard), a small asset-scope enum/mapping (`stocks|crypto|both` → `AssetCategory` set). No migration.
- **Frontend**: `pages/portfolios/BuildAIPortfolioCard.tsx` (capital default `10000`, asset-type selector), `types/api.ts` (`AIPortfolioBuildRequest.asset_types`), `lib/format.ts` (`formatCurrency` → USD), and remaining per-file EUR `Intl.NumberFormat` instances (e.g. `PaperTradingSessionPage.tsx`) switched to USD.
- **Tests**: backend — default capital, scope filtering at build/rebalance, discovery rejection outside scope, `session_metadata` round-trip; frontend — form default `10000`, asset-type selector wiring, USD formatting.
