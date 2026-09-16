## Context

Asset metrics are FX-normalized to EUR today. The chain is: `market_data.fetch_fx_rate(currency)`
returns a `currency → EUR` rate (pair `{currency}EUR=X`, `1.0` for EUR);
`metrics.py` multiplies native price/market-cap/turnover by that rate to produce
`price_eur`, `market_cap_eur`, `avg_daily_turnover_eur`; those normalized values
are persisted (`assets.market_cap_eur`, `assets.avg_daily_turnover_eur`),
evaluated against EUR constants in `constants.py` via `evaluation.py`, exposed on
`AssetRead`, and displayed with `€` on the Assets page. The recent universe switch
to US listings makes EUR the odd currency out.

The schema is owned by Alembic; models never `create_all`. The DB currently has a
single linear migration head. Existing asset rows hold EUR-normalized values.

## Goals / Non-Goals

**Goals:**
- Normalize asset metrics to USD end to end (FX target, storage, thresholds,
  evaluator, API, frontend).
- Keep the eligibility screening floors at their current numeric magnitudes,
  reinterpreted as USD.
- Rename the persisted metric columns to `*_usd` with a reversible migration; do
  not backfill existing values.

**Non-Goals:**
- Recalibrating the threshold magnitudes (no FX conversion of the floors).
- Backfilling/re-deriving existing rows' stored values (they refresh on re-add).
- Any change to non-asset money display (already USD) or to the criterion `name`
  strings (`price`, `market_cap`, … — a public contract the frontend depends on).

## Decisions

### FX normalization target EUR → USD
`MarketDataProvider.fetch_fx_rate(currency)` returns a `currency → USD` rate:
`1.0` when `currency == "USD"`, otherwise the yfinance pair `{currency}USD=X`.
`metrics.py` renames its derived fields to `price_usd`, `market_cap_usd`,
`avg_daily_turnover_usd` (the `_convert(value, rate) = value * rate` helper is
unchanged; only the rate's target currency changes). Docstrings updated EUR→USD.

### Thresholds: relabel, don't reconvert
Rename the constants `MIN_PRICE_EUR → MIN_PRICE_USD`,
`MIN_AVG_DAILY_TURNOVER_EUR → MIN_AVG_DAILY_TURNOVER_USD`,
`MIN_MARKET_CAP_EUR → MIN_MARKET_CAP_USD`,
`MIN_CRYPTO_AVG_DAILY_TURNOVER_EUR → …_USD`,
`MIN_CRYPTO_MARKET_CAP_EUR → …_USD`, keeping the same numeric values
(`5`, `2_000_000`, `1_000_000_000`, `10_000_000`, `2_000_000_000`). The module
docstring changes "expressed in EUR" → "expressed in USD". These are
order-of-magnitude screening floors and EUR≈USD, so relabeling is truthful and
avoids baking a rate into the thresholds.

### Evaluator field rename
`evaluation.AssetMetrics` fields become `price_usd`, `avg_daily_turnover_usd`,
`market_cap_usd`; the `_CriterionSpec` metric accessors and the imported
threshold constants follow. The criterion `name` values are unchanged.

### Column rename via Alembic (no backfill)
New migration with `down_revision` = current head. `upgrade` runs
`op.alter_column("assets", "market_cap_eur", new_column_name="market_cap_usd")`
and the same for `avg_daily_turnover_eur → avg_daily_turnover_usd`; `downgrade`
reverses both. `models.py` maps the columns to `market_cap_usd` /
`avg_daily_turnover_usd`. Existing rows keep their (EUR-derived) numbers under
the new names — accepted per the chosen approach; they re-derive in USD on the
next add/refresh. The single linear head is preserved.

### API + frontend field rename
`AssetRead` exposes `market_cap_usd` / `avg_daily_turnover_usd`. Frontend
`types/api.ts` `Asset` mirrors the rename; `AssetsPage.tsx` swaps the compact
`€` formatter for a `$` one, retitles the columns `Market Cap ($)` /
`Avg Daily Turnover ($)`, and renders the eligibility-criteria thresholds with
the `$` formatter. This realizes the already-specified "Monetary values
displayed in USD (across all views)" behavior, so no `app-shell` spec delta.

## Risks / Trade-offs

- **Stale pre-existing rows:** rows added before this change keep EUR-magnitude
  values under `*_usd` names until re-derived — displayed figures may be ~10%
  off and screened against USD floors they were not computed for. Accepted:
  EUR≈USD keeps this within screening noise, and rows refresh on re-add. A
  re-derive backfill was explicitly declined.
- **Grep completeness:** `*_eur` names thread through metrics, evaluation,
  constants, models, schema, the frontend, and many tests. Mitigation: a
  repo-wide `_eur`/`EUR`/`€` sweep after the edits, plus the full backend and
  frontend gates.
- **Reversible migration:** `alter_column` rename is reversible and touches no
  data, so `upgrade`/`downgrade` round-trips cleanly and `alembic check` stays
  drift-free.
