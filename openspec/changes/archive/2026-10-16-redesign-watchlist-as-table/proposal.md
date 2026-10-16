## Why

The Watchlist page renders a vertical card list where each card inlines the asset's
SEC EDGAR fundamentals and its short-window technical-indicator panel. As the
watchlist grows this is hard to scan, cannot be searched/sorted/filtered the way the
Assets page can, and duplicates detail-level data on a list screen. Meanwhile the
shared asset detail page (`/assets/:ticker`) shows only price/snapshot/company facts —
it is the natural home for fundamentals and technical indicators but surfaces neither.

## What Changes

- **Watchlist page becomes a table.** Replace the card list (with its inline
  `FundamentalsPanel` / `TechnicalPanel`) with a searchable, sortable, filterable
  table that mirrors the Assets page: debounced search, sortable ticker/name columns,
  and category/sector multi-select filters. Each row links to the asset detail page.
  The "Discover emerging companies" recommendation card stays above the table.
- **Watchlist list fetch gains full query controls.** The frontend watchlist fetch
  moves from the single fixed 100-row `listWatchlist()` page to the paginated
  `listAssets` path with `membership: 'watchlist'`, threading `membership` through
  `AssetsListParams` / `listAssets` / `useAssets` (the backend list endpoint already
  supports the `membership` param). Search/sort/category/sector filtering is applied
  server-side, matching the Assets page behavior.
- **Asset detail page shows fundamentals + technical indicators.** The shared detail
  page gains two new sections: **Fundamentals** (rendered when the asset has a
  fundamentals row; otherwise an "unavailable" note) and **Technical indicators**
  (the short-window profile, with an explicit insufficient-history state when the
  asset's history is below the floor). These sections render for **every** asset
  (universe and watchlist) via one read path — fundamentals happen to be populated for
  watchlist assets today; the short-window technical profile is available for any
  asset with a stored indicator snapshot.
- **Backend seams to feed the detail page:**
  - The asset detail read (`GET /api/v1/assets/{ticker}/details`) gains the asset's
    available fundamentals (null when none has been fetched).
  - A new per-asset short-window technical read exposes the short-window profile +
    minimum-history floor + insufficient-history marker for a single asset by ticker,
    for universe and watchlist assets alike (the existing batched read is
    watchlist-membership-only; the underlying snapshots already exist for universe
    assets via the universe-wide precompute). The long-window uptrend trend-gate
    verdict is still not presented as a trading signal.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `assets`: "View asset detail with a daily snapshot" — the single-asset detail read
  also returns the asset's available SEC EDGAR fundamentals (null when none exists).
- `technical-indicators`: a per-asset short-window indicator read — expose the
  short-window profile + minimum-history floor + insufficient-history marker for a
  single asset by ticker, for any membership, without the uptrend trend-gate verdict.
- `app-shell`: the old "Watchlist view" requirement is replaced by a new "Watchlist
  table view" requirement — the watchlist is presented as a searchable / sortable /
  filterable table whose rows link to the asset detail page, with fundamentals and
  technical indicators no longer rendered inline on the watchlist (they move to the
  detail page); plus a new "Asset detail fundamentals and technical indicators"
  requirement for the asset detail view showing the asset's available fundamentals and
  short-window technical-indicator profile (with an insufficient-history state).

## Impact

- **Backend:** `api/schemas.py` (`AssetDetailRead` gains fundamentals); `assets/service.py`
  (`get_asset_detail` loads the fundamentals relationship); `assets/routers`
  (map fundamentals onto the detail response); `technical_indicators/service.py`
  (a single-asset short-window read reusing the existing snapshot builder, not
  membership-filtered); `api/routers/technical_indicators.py` (new per-asset route);
  new response schema for the per-asset technical read. No migration (reuses existing
  `asset_fundamentals` and `technical_indicator` tables).
- **Frontend:** `api/assets.ts` (`AssetsListParams`/`listAssets`/`useAssets` gain
  `membership`; `AssetDetail` type gains fundamentals); `api/technicalIndicators.ts`
  (new per-asset indicator fetch + hook); `pages/watchlist/WatchlistPage.tsx`
  (rebuilt as a table, reusing the Assets table/search/sort/filter pattern; inline
  fundamentals/technical panels removed); `pages/assets/AssetDetailPage.tsx` (new
  Fundamentals + Technical-indicators sections, reusing the fundamentals/technical
  rendering extracted from the old watchlist cards); `types/api.ts`. Co-located
  Vitest tests updated for all of the above.
- **No change** to: when indicators/fundamentals are computed, the cron/precompute
  jobs, the universe trend gate or any trading flow, routing (`/assets/:ticker`
  already exists and is shared), or the Assets page itself.
