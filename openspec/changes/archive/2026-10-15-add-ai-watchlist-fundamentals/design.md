# Design: AI watchlist with SEC EDGAR fundamentals

## Context

See proposal.md — Why. Key constraints from the existing codebase:

- Watchlist items are `assets` rows (same table) distinguished by a column, per
  the user's decision — so promotion and later fundamentals-for-eligible-assets
  need no second model.
- `list_assets(session, ...)` in `assets/service.py` is the de-facto "the
  universe" read: it is called unfiltered by **all** trading/analytics paths —
  `ai_portfolio/flows/{build,rebalance,close}.py`, `ai_portfolio/stop_loss.py`,
  `ai_portfolio/events.py`, `dashboard/service.py`, the price-history ingest in
  `api/routers/ai_portfolio.py`, the recommender exclusion in
  `recommendations/service.py`, and the assets list router. `get_universe_assets`
  (used by the universe evaluation) is a second such read.
- Eligibility is already informational, not a precondition to trade (crypto
  requirement). The maturity gates (history, market cap) are what exclude young
  companies; executability gates (brokerage-tradable, supported category) are
  the hard floor that `add_asset` already enforces via `broker.get_asset`.
- All market network access is confined to provider seams
  (`MarketDataProvider`); tests fake the seam.

## Goals / Non-Goals

**Goals**
- Isolate watchlist assets from every universe read with the least churn.
- Reuse the recommendations run machinery for a watchlist-targeted mode.
- Add a general-purpose per-asset fundamentals store fed by a fakeable EDGAR seam.

**Non-Goals (design-level)**
- No change to order routing, sizing, or any executor behavior.
- No derived fundamental indicators / `quality_pass` screen (raw storage only).
- No fundamentals for existing universe assets in this change (store enables it).

## Decisions

### D1. Isolation via a `list_assets` default, not per-caller edits
Add `membership: AssetMembership | None = AssetMembership.UNIVERSE` to
`list_assets`/`count_assets` and filter `get_universe_assets` to `universe`.
Because the **default** is universe-only, every existing unfiltered caller
(build/rebalance/close/stop-loss/events/dashboard/price-history ingest) keeps
its current meaning with **zero edits** — watchlist rows simply never appear.
Only two callers opt out of the default:
- the recommender exclusion list → `membership=None` (dedupe against *all*
  assets, universe + watchlist), and
- the watchlist listing → `membership="watchlist"`.

*Alternative considered:* a separate `watchlist` table. Rejected per the user —
blocks cheap promotion and a shared fundamentals store. *Alternative:* edit each
of the ~8 universe callers to pass a filter. Rejected — large surface, easy to
miss one and silently leak a watchlist name into trading.

### D2. `membership` column: non-null string enum, default `universe`, backfilled
Mirror the existing `category`/`sector` string-column style (`AssetMembership`
str enum: `UNIVERSE`, `WATCHLIST`). Migration adds the column
`server_default='universe'`, backfills existing rows, keeps it `NOT NULL`, and
indexed (filtered on every list). `down_revision = e1f2a3b4c5d6` (current head).

### D3. Recommendation run gains a `target`
Add `target: str` (`universe` default / `watchlist`) to `RecommendationRun`
(migration, same head chain) and to the queue request schema. The background
worker branches on target to pick the prompt builder and the per-candidate add
path. Watchlist runs are validated to **stock-only** at the queue boundary
(EDGAR is equities-only). A single in-flight run at a time is unchanged.

### D4. Watchlist add path relaxes maturity, keeps executability
Reuse `add_asset`'s fetch → category check → `broker.get_asset` tradability
check, but persist with `membership=watchlist` and **do not** treat ineligibility
as a rejection (it never was — eligibility is just a stored flag). The watchlist
differs from the universe run only in: the prompt (emerging companies), the
membership stamped, and the fundamentals fetch afterward. Dedupe is by existence
against all assets (the normalized-ticker duplicate check already covers this).

### D5. EDGAR seam + fundamentals storage
New `FundamentalsProvider` protocol (sync, fakeable) with a single
`SecEdgarFundamentalsProvider` implementation confining HTTP to EDGAR
(`company_tickers.json` for ticker→CIK, `companyfacts` for XBRL facts; a
descriptive `User-Agent` is required by EDGAR and read from config). It returns a
plain dataclass of the raw figures (revenue, gross/operating/net margin inputs,
operating cash flow, earnings/EPS, plus company details) — no derivation.
Persist as a new `asset_fundamentals` table keyed by `asset_id` (1:1, mostly a
JSONB `document` plus a `fetched_at` and a `source`/`status` marker), so it is
general-purpose and a later change can populate it for universe assets.
Fetch is best-effort: failures record `status=unavailable`, never block creation.

*Alternative considered:* JSONB column on `assets`. Rejected — a dedicated table
keeps the assets row lean and makes "has fundamentals?" queries and future
per-statement columns cleaner. *Alternative:* yfinance / Alpha Vantage. Rejected
earlier (determinism; Alpha Vantage free tier is 25 req/day).

### D6. Frontend Watchlist page reuses AI-run polling
New route + sidebar entry. The page triggers a watchlist-targeted recommendation
run (same polling hook as recommendations) and lists `membership=watchlist`
assets with their fundamentals via a new read field/endpoint.

## Risks / Trade-offs

- **A universe read is missed and a watchlist name leaks into trading** → D1's
  default-universe makes leakage the *non-default*; a test asserts watchlist
  assets are absent from `list_assets()`/`get_universe_assets()` defaults and
  from build/rebalance candidates.
- **EDGAR rate-limiting / flaky responses** → best-effort fetch (D5) never fails
  creation; EDGAR asks for ≤10 req/s and a `User-Agent`; fetch is one-shot at
  creation (no bulk loop), well under limits.
- **Ticker→CIK mismatch (class shares, changed tickers)** → unresolved CIK is a
  graceful `unavailable`, not an error; surfaced in the UI as "no fundamentals".
- **Emerging-company prompt returns thinly-traded/untradable names** → the
  brokerage tradability floor (D4) rejects them with a recorded outcome.

## Migration Plan

1. One Alembic migration (head `e1f2a3b4c5d6`): add `assets.membership`
   (default `universe`, backfill, NOT NULL, indexed); add `recommendation_runs.target`
   (default `universe`, backfill, NOT NULL); create `asset_fundamentals`.
2. Deploy is additive and backward compatible — existing rows become universe
   members; no behavior changes until a watchlist run is triggered.
3. Rollback: downgrade drops the column/table; watchlist rows (if any) would be
   orphaned as plain assets — acceptable for a pre-use feature, but prefer
   deleting watchlist rows before downgrade.
