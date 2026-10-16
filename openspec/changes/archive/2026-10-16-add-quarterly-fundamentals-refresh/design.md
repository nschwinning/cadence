## Context

See proposal.md — Why. Today fundamentals are fetched once, under the watchlist
add path (`record_fundamentals` in `assets/service.py`, called from
`recommendations/service.py` behind an `is_watchlist` guard reached only after a
successful `add_asset`). The persistence seam is already general-purpose per asset
and best-effort: `record_fundamentals(session, asset, provider)` upserts the
single 1:1 `asset_fundamentals` row (insert, else overwrite source/status/cik/
document and refresh `fetched_at`), and `SecEdgarFundamentalsProvider`
(`assets/fundamentals.py`) never raises — any failure degrades to
`Fundamentals.unavailable()`. What is missing is a caller that drives it across
the stock universe on a schedule.

The project already has an established cron pattern: cron-guarded POST endpoints
(`require_valid_cron_token` / `X-Cron-Token`) invoked by sidecar shell scripts in
`docker-compose.yml`, each driven by a `*_SCHEDULE` setting (rebalance, crypto
rebalance, benchmark, snapshot, indicators). This change follows that pattern
exactly.

## Goals / Non-Goals

**Goals:**
- Keep stock fundamentals reasonably current with quarterly SEC filings by
  re-fetching every stock asset on a quarterly cron.
- Reuse the existing upsert and provider seams rather than add new fetch logic.
- Make the batch best-effort per asset and observable via a returned summary.

**Non-Goals:**
- No staleness/TTL logic or max-age column — every run refreshes all stocks.
- No DB migration, no schema change, no frontend change, no crypto fundamentals.

## Decisions

### 1. New batch service function reusing `record_fundamentals`
Add `refresh_stock_fundamentals(session, provider)` to `assets/service.py`. It
selects all `Asset` rows with `category == stock` (deterministic order, e.g. by
ticker), calls `record_fundamentals(session, asset, provider)` per asset inside a
try/except so one asset's unexpected error cannot abort the batch, and returns a
small summary dataclass (counts: `stocks_considered`, `refreshed`, and a
breakdown by resulting status — available/partial/unavailable). Reusing
`record_fundamentals` means the upsert, the 1:1 guarantee, and the
degrade-to-unavailable behavior are inherited unchanged.

*Alternative considered:* a brand-new fetch+persist path specific to the job —
rejected; it would duplicate the upsert and the provider seam and drift from the
add-time behavior.

### 2. Cron-guarded endpoint on the assets router
Add `POST /api/v1/assets/fundamentals/refresh`, guarded by
`require_valid_cron_token`, that resolves the provider via the existing
`get_fundamentals_provider()` factory, calls the service, and returns the summary
(new response schema in `api/schemas.py`). Placing it on the assets router keeps
fundamentals within the `assets` capability.

*Alternative considered:* a queued/polled background job like the AI runs —
rejected as over-engineered; this is a simple synchronous batch with no
user-facing progress, matching the snapshot/indicators cron jobs which run
synchronously within the request.

### 3. Quarterly schedule via `FUNDAMENTALS_SCHEDULE` + sidecar script
Add a `FUNDAMENTALS_SCHEDULE` setting (default `0 6 1 1,4,7,10 *` — 06:00 on the
1st of Jan/Apr/Jul/Oct, after quarter-ends when fresh 10-Q/10-K data is
available) and a `fundamentals.sh` sidecar script + `docker-compose.yml` cron
entry mirroring `indicators.sh`. Reuse `REBALANCE_CRON_TOKEN` (the shared cron
secret) rather than introduce a new token.

### 4. Centralize add-time fetch in the creation path
Move the add-time fundamentals fetch into the `add_asset` creation path so every
stock-creation path gets it uniformly (manual add endpoint, watchlist AI run,
universe AI run). `add_asset` fetches fundamentals (best-effort via
`record_fundamentals`) only for `category == stock` assets, so crypto creation is
untouched. The current watchlist-only call in `recommendations/service.py` then
becomes redundant and is removed, eliminating the special case. The provider is
passed into `add_asset` from the injected `get_fundamentals_provider()` factory,
consistent with how routers and the recommendation runner already wire providers.

*Alternative considered:* add fetch-on-add only to the manual endpoint and leave
the watchlist path as-is — rejected; it leaves universe-recommendation-added
stocks without fundamentals and keeps two divergent fetch sites.

### 5. SEC EDGAR politeness
The provider issues sequential `httpx` calls per asset (ticker→CIK map is loaded
once and can be cached for the run; then companyfacts + submissions per asset).
The batch stays sequential — no parallel fan-out — to respect EDGAR's ≤10 req/s
guidance. If needed, a small inter-asset delay can be added, but sequential
single-threaded fetching over a few hundred stocks four times a year is already
well within EDGAR limits, so no explicit rate limiter is introduced.

## Migration Plan

- **One-time backfill**: existing stocks that never had fundamentals are
  populated by invoking the refresh endpoint once after deploy
  (`POST /api/v1/assets/fundamentals/refresh` with the cron token). No separate
  backfill script is needed — the quarterly job's behavior (re-fetch all stocks)
  is exactly the backfill. From then on, fetch-on-creation keeps new stocks
  current and the quarterly cron keeps all stocks fresh.
- **Rollback**: the job is additive and idempotent (re-running re-fetches and
  upserts). Disabling the cron entry and omitting the one-time invocation fully
  reverts to the prior behavior; no data migration to undo.

## Risks / Trade-offs

- **Full-universe re-fetch each run is more EDGAR traffic than a stale-only
  refresh** → Accepted deliberately (user decision) because filings are quarterly
  and the run is infrequent; sequential fetching keeps it polite and the volume
  bounded.
- **A long batch runs inside one request** → Low risk at quarterly cadence and
  current universe size; the sidecar script's curl timeout should allow for it.
  If the universe grows large enough to matter, the job can move to a queued
  background worker later without changing the spec's observable behavior.
- **Transient EDGAR outage during a run** → Best-effort per asset means affected
  assets are recorded unavailable and corrected on the next quarterly run;
  summary counts make a bad run visible.
