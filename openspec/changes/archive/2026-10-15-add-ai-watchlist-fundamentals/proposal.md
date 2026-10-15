## Why

Cadence's eligibility gate deliberately excludes young companies (the 5-year
history and $1B market-cap maturity floors), so promising emerging names in hot
sectors can never surface for research until they are already large. We want a
**watchlist**: an AI-curated set of emerging-but-currently-ineligible companies
the operator can track (with real fundamentals) ahead of any future decision to
trade them. Storing watchlist items as first-class assets — distinguished by a
single column — lets us later promote them into the tradable universe and later
attach fundamentals to eligible assets too, without a second data model.

## What Changes

- **Asset membership.** Add a `membership` attribute to every asset
  (`universe` by default, or `watchlist`). Existing rows backfill to `universe`.
  Membership is **orthogonal to eligibility** — a watchlist asset is still
  evaluated and flagged like any other; it just lives in a separate bucket.
- **Isolation (BREAKING for internal universe reads).** Every existing "the
  universe" read — the recommender's exclusion/aggregates, the AI-portfolio
  build/rebalance candidate set, the universe-evaluation summary, and the
  default asset list — SHALL filter to `membership = universe` so watchlist
  items never leak into trading, evaluation, or the universe management page.
- **Watchlist AI recommendation.** A recommendation run can target the
  **watchlist** (vs the default universe). A watchlist run uses a distinct
  prompt that explicitly seeks **emerging companies from promising sectors**,
  **relaxes the maturity gates** (it adds immature names on purpose) while
  keeping the executability floor (real, brokerage-tradable US **stock**), and
  dedupes against **all** assets (universe or watchlist). Added candidates are
  persisted with `membership = watchlist`.
- **SEC EDGAR fundamentals.** When a watchlist asset is created, fetch its
  fundamentals from SEC EDGAR (company-facts/XBRL, resolved via a ticker→CIK
  map) — revenue, margin inputs, cash flow, earnings, and company details — and
  persist them per asset. Fetching degrades gracefully when EDGAR has no data.
  Storage is general-purpose per asset so eligible assets can gain fundamentals
  in a later change.
- **Watchlist page.** A new frontend view to trigger a watchlist recommendation
  run (reusing the existing AI-run polling) and browse watchlist entries with
  their fundamentals.

## Capabilities

### New Capabilities
<!-- None: watchlist items are assets; the page is part of the existing shell. -->

### Modified Capabilities
- `assets`: add the `membership` classification (with universe-read isolation and
  backfill); add SEC EDGAR fundamentals fetch + persistence; the asset list
  gains a membership filter and defaults to universe members.
- `asset-recommendations`: a run can target the watchlist; a new watchlist
  execution mode that seeks emerging companies, relaxes maturity gating, keeps
  the executability/stock/dedupe floor, adds watchlist members, and triggers
  fundamentals fetch.
- `app-shell`: a new Watchlist navigation entry and view (trigger recommendation
  + list entries with fundamentals).

## Impact

- **Backend:** `assets/models.py` (new `membership` column + a fundamentals
  store), new Alembic migration (nullable→backfilled `membership`, fundamentals
  table), `assets/service.py` (`get_universe_assets` + list filtering + creation
  path), `assets/market_data.py` / a new EDGAR provider seam (network confined,
  fakeable), `recommendations/{service,background,agent,constants}.py` +
  `api/routers/recommendations.py` (watchlist target + prompt), `api/schemas.py`,
  and the AI-portfolio / universe-evaluation universe reads (isolation).
- **Frontend:** new Watchlist page + nav entry, `api/` client types for
  membership + fundamentals, reused AI-run polling.
- **External dependency:** SEC EDGAR HTTP API (free, no key; requires a
  descriptive `User-Agent`). Equities-only — crypto has no filings.
- **Out of scope (future changes):** opting the watchlist into portfolio
  build/rebalance; a promotion workflow; derived fundamental indicators and a
  `quality_pass` screen; relaxing the universe's own eligibility criteria;
  backfilling fundamentals for existing eligible assets; scheduled fundamentals
  refresh; crypto fundamentals.
