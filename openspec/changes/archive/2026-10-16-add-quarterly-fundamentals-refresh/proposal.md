## Why

Asset fundamentals (SEC EDGAR) are fetched exactly once per asset — only when a
new equity is first added to the watchlist during a recommendation run — and are
then never refreshed: there is no cron job, no staleness check, and `fetched_at`
is stored but never read. Because SEC 10‑Q/10‑K filings are quarterly, stored
fundamentals go stale indefinitely, and universe or manually-added stocks may
never get fundamentals at all, misinforming the asset detail page.

## What Changes

- Add a **quarterly, cron-driven refresh job** that re-fetches SEC EDGAR
  fundamentals for **every stock asset** in the universe on each run (no
  staleness threshold — all stocks are refreshed every run), reusing the existing
  `record_fundamentals` upsert so each asset's single 1:1 fundamentals row is
  updated in place and its `fetched_at` advanced.
- Scope is **all `category = stock` assets**, regardless of membership (universe
  or watchlist) or eligibility/tradability. Crypto is excluded (SEC EDGAR covers
  US company filers). Tickers EDGAR cannot resolve simply persist as
  `status = unavailable`, as today.
- The refresh is **best-effort per asset**: one asset's fetch failure SHALL NOT
  abort the batch, and the job returns a small summary (counts of stocks seen /
  refreshed / available / partial / unavailable) for observability.
- Expose the refresh behind a new **cron-guarded endpoint** (protected by the
  existing `X-Cron-Token` shared secret, like the rebalance / snapshot /
  indicators jobs) and drive it from a new **cron sidecar entry** on a new
  `FUNDAMENTALS_SCHEDULE` (default quarterly).
- **Fetch fundamentals on creation for every new stock asset**, through any path
  (manual add or an AI recommendation run, any membership) — broadening today's
  watchlist-only, add-time fetch so a newly added stock has fundamentals
  immediately rather than waiting for the next quarterly run. Crypto creation
  still does not fetch fundamentals.
- **One-time backfill** of existing stocks that have no fundamentals: because the
  quarterly refresh re-fetches all stock assets, the backfill is performed by
  invoking the refresh endpoint once at deploy (a documented operational step, no
  throwaway code).

## Capabilities

### New Capabilities

<!-- none -->

### Modified Capabilities

- `assets`: (1) ADD a requirement that stock fundamentals are **periodically
  refreshed on a quarterly schedule across all stock assets** via a cron-guarded,
  best-effort batch job that reuses the existing per-asset fundamentals upsert;
  and (2) MODIFY "Fetch and persist company fundamentals from SEC EDGAR" to fetch
  fundamentals on creation for **any stock (equity) asset through any path**
  (not watchlist-only), while crypto creation still does not fetch.

## Impact

- **Backend code**: new batch service function in `assets/service.py`
  (`refresh_stock_fundamentals`), reusing `record_fundamentals` and the existing
  `SecEdgarFundamentalsProvider` / `FundamentalsProvider` seam
  (`assets/fundamentals.py`); new cron-guarded route (e.g.
  `POST /api/v1/assets/fundamentals/refresh`) on the assets router using
  `require_valid_cron_token`; new summary response schema in `api/schemas.py`.
  Centralize the add-time fetch so every stock-creation path fetches
  fundamentals: the `add_asset` creation path (used by the manual add endpoint and
  the recommendation runner) fetches for stock assets, which lets the current
  watchlist-only call in `recommendations/service.py` be removed as redundant.
- **Config**: new `FUNDAMENTALS_SCHEDULE` setting (default quarterly cron
  `0 6 1 1,4,7,10 *`); reuses `REBALANCE_CRON_TOKEN` and the existing
  `SEC_EDGAR_*` provider settings.
- **Deployment**: new cron sidecar script + `docker-compose.yml` cron entry
  mirroring the existing `indicators.sh` / `rebalance.sh` jobs.
- **Deployment (one-time)**: after rollout, invoke the refresh endpoint once to
  backfill fundamentals for existing stocks.
- **No DB migration** (the `asset_fundamentals` model and `fetched_at` already
  exist; the upsert path is unchanged). **No frontend change** (the asset detail
  page already renders fundamentals and an unavailable note). **No staleness/TTL
  column or setting.**
- **External**: increased, but bounded and infrequent (quarterly), SEC EDGAR
  request volume across the full stock universe; the job must respect EDGAR's
  politeness guidance rather than issue parallel bursts.
