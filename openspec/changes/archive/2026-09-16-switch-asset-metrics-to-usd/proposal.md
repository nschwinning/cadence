## Why

The asset universe was switched to US listings, and the app now displays money in
US dollars everywhere else. But asset metrics are still FX-normalized to **EUR**:
the market-data layer converts every asset to EUR, the `assets` table stores
`market_cap_eur` / `avg_daily_turnover_eur`, eligibility is screened against
EUR thresholds, and the Assets page still shows `€` market-cap and turnover
figures. For a US-dollar universe this is an inconsistent and confusing second
currency. This change makes the dollar the single currency end to end.

## What Changes

- Switch the FX normalization target from EUR to **USD**: the market-data
  provider returns a `currency → USD` rate (1.0 for USD), and metric derivation
  normalizes price, market cap, and average daily turnover to USD.
- Rename the normalized metric columns `market_cap_eur → market_cap_usd` and
  `avg_daily_turnover_eur → avg_daily_turnover_usd` via an Alembic migration.
  Existing rows keep their current numeric values (no backfill); they are
  re-derived in USD the next time an asset is re-added/refreshed.
- Keep the eligibility screening floors at their **current numeric magnitudes**,
  reinterpreted as USD (e.g. market cap `> $1B`, price `> $5`, turnover
  `≥ $2M`, crypto turnover `≥ $10M`, crypto market cap `> $2B`). They are
  order-of-magnitude screening floors and EUR≈USD, so relabeling avoids false
  precision.
- Rename the EUR threshold constants (`MIN_*_EUR → MIN_*_USD`) and the
  evaluator's metric fields (`price_eur/market_cap_eur/avg_daily_turnover_eur →
  *_usd`); update the API `AssetRead` fields to `*_usd`.
- Frontend Assets page: show market cap and average daily turnover in USD
  (`$` compact formatter, `Market Cap ($)` / `Avg Daily Turnover ($)` headers),
  and render the eligibility-criteria thresholds in USD.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `assets`: the "EUR-based eligibility evaluation" requirement becomes
  USD-based — figures are normalized to USD via a current FX rate and screened
  against USD-denominated thresholds; the stored/exposed normalized metrics are
  in USD.

## Impact

- **Backend:** `assets/market_data.py` (`fetch_fx_rate` → USD pair),
  `assets/metrics.py` (USD conversion + field names), `assets/constants.py`
  (`MIN_*_USD`), `assets/evaluation.py` (`AssetMetrics.*_usd`, criterion
  thresholds), `assets/models.py` (column rename), `api/schemas.py`
  (`AssetRead.*_usd`), a new Alembic migration, and the affected tests.
- **Frontend:** `pages/assets/AssetsPage.tsx` (compact `$` formatter + headers +
  criteria threshold rendering), `types/api.ts` (`*_usd` fields), and the
  co-located tests.
- **Data:** the `assets` table columns are renamed; pre-existing normalized
  values remain until each asset is next re-derived. No display or API contract
  outside the renamed metric fields changes.
- The Assets page dollar display realizes the already-specified "Monetary values
  displayed in USD (across all views)" behavior; no `app-shell` requirement
  change is needed.
