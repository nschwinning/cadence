# Category-specific eligibility and authoritative brokerage tradability

## Why

Two add-time behaviors were implemented in code but never captured in the spec,
leaving `specs/assets/spec.md` describing older behavior:

1. **Uniform eligibility criteria were wrong for crypto.** Every asset was scored
   against the same four EUR thresholds (price > €5, turnover ≥ €2M, market cap >
   €1B, history ≥ 5y). That profile is inappropriate for crypto: per-unit price is
   meaningless (it depends on token supply, not value), and a 5-year history
   excludes established coins from a younger asset class.

2. **Tradability was a guess, not a fact.** Cadence trades its universe on Alpaca,
   but nothing proved an asset was actually tradable there, and the exact symbol
   Alpaca expects (e.g. yfinance `BTC-USD` vs Alpaca `BTC/USD`) had to be
   reconstructed at trade time. A prior dot-heuristic ("reject tickers containing a
   `.`") only guessed at foreign listings.

## What Changes

- **Category-specific eligibility criteria.** Eligibility is evaluated against a
  per-category criteria profile. Equities keep the four existing criteria. Crypto
  uses a distinct profile that **omits the per-unit price criterion** and applies
  its own thresholds — a **shorter** minimum history and **higher** liquidity and
  market-capitalization floors — reflecting the asset class. Each criterion's
  name, outcome, observed value, and threshold are still recorded per asset.
- **Authoritative brokerage tradability + stored canonical symbol.** At add time
  the asset is looked up on the brokerage; it is rejected unless the brokerage
  lists it as tradable, and the brokerage's canonical symbol is captured and stored
  on the asset. If the brokerage is unconfigured or unreachable the add fails and
  nothing is persisted. (Order routing continues to derive the trade symbol as
  before — consuming the stored symbol is a separate, later change.)

## Impact

- Affected specs: `assets` — MODIFIED "Add an asset by ticker" (brokerage
  tradability verification + stored canonical symbol) and "EUR-based eligibility
  evaluation" (category-specific criteria).
- Affected code (already implemented): `assets/constants.py` (crypto thresholds),
  `assets/evaluation.py` (per-category criteria profiles), `assets/service.py`
  (`evaluate(metrics, category)`; brokerage `get_asset` gate + `alpaca_symbol`
  persistence), `assets/models.py` (+ `alpaca_symbol` column), `broker/*`
  (`get_asset` on the `Broker` protocol, Alpaca + stub impls, `BrokerAsset`),
  `api/routers/assets.py` + `api/app.py` (503 on brokerage unavailability),
  `api/schemas.py` (`alpaca_symbol`), recommender/ai-portfolio add paths (broker
  threaded through); frontend `types/api.ts` (+ `alpaca_symbol`) and
  `AssetsPage.tsx` (threshold-derived criterion labels). Backend + frontend tests.
- Database: one migration adds a nullable `assets.alpaca_symbol` column + index
  (`c4e7a1f9b2d3`). Legacy rows stay NULL; new adds always populate it.
- Retroactive: this change documents behavior already merged to the working tree;
  tasks are checked off as verification rather than net-new work.
