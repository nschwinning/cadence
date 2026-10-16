## Context

See proposal.md — Why. Relevant current-state constraints:

- `GET /api/v1/assets/{ticker}/details` → `AssetDetailRead` (api/schemas.py) is
  hand-built in the router from asset profile fields + the daily snapshot; it does
  not touch `Asset.fundamentals` or any `TechnicalIndicator` row.
- Fundamentals live on the `Asset.fundamentals` 1:1 relationship (populated for
  watchlist assets today; relationship supports universe) and are only surfaced
  embedded in `AssetRead` (list/create), via `AssetFundamentalsRead`.
- Technical snapshots: `GET /api/v1/technical-indicators/watchlist` is
  **watchlist-membership-only** (`get_watchlist_indicators` filters
  `Asset.membership == WATCHLIST`). The short-window `WatchlistIndicatorSnapshot`
  builder and `WatchlistIndicatorRead` schema already exist. The underlying
  `TechnicalIndicator` rows are computed universe-wide by the nightly precompute, so
  snapshots exist for universe assets too — they are just not exposed per asset.
- `GET /api/v1/assets` already accepts `membership`, `search`, `sort`, `direction`,
  repeatable `category`/`sector`, and `limit`/`offset`. Frontend `listAssets` /
  `AssetsListParams` / `useAssets` do **not** thread `membership`; `useWatchlist`
  is a separate single fixed 100-row fetch (`membership: 'watchlist'`, no controls).
- `/assets/:ticker` → `AssetDetailPage` already exists and is shared.

## Goals / Non-Goals

**Goals:**
- Watchlist page = searchable/sortable/filterable table with Assets-parity controls,
  rows linking to `/assets/:ticker`.
- Fundamentals + short-window technicals shown on the shared detail page for any asset
  via one read path each, with an insufficient-history state for technicals.
- Reuse existing building blocks: the Assets table/search/sort/filter pattern, the
  `WatchlistIndicatorSnapshot` short-window builder, `AssetFundamentalsRead`, and the
  fundamentals/technical rendering extracted from the current watchlist cards.

**Non-Goals:**
- No change to when/how indicators or fundamentals are computed (no new precompute,
  no fundamentals fetch on detail read, no cron changes).
- No universe trend-gate / long-window verdict on the detail page; no trading-flow
  change.
- No new DB table/column/migration (reuse `asset_fundamentals` + `technical_indicator`).
- No change to the Assets page or to `/assets/:ticker` routing (already shared).

## Decisions

### D1 — Fundamentals delivered on the existing detail read (not a new endpoint)

Add `fundamentals: AssetFundamentalsRead | None` to `AssetDetailRead` and have
`get_asset_detail` load the `Asset.fundamentals` relationship so the router maps it
onto the response. The detail page already fetches `/details`; this keeps fundamentals
a single read with no extra round-trip.

- **Why not a new per-asset fundamentals endpoint?** `AssetFundamentalsRead` is already
  a reusable embedded schema; the detail read is the one place the page needs it. A
  separate endpoint adds a route + a fetch for no benefit.
- Reading the relationship must not trigger a fetch (fundamentals are populated by the
  recommendation flow only); absent fundamentals → `null`, never a 500.

### D2 — A dedicated per-asset technical read (not embedded in `AssetDetailRead`)

Add a new read `GET /api/v1/technical-indicators/assets/{ticker}` returning
`{ min_bars, indicator: WatchlistIndicatorRead | null }` for an asset of **any**
membership. Implement with a single-asset variant of the snapshot builder that does
**not** apply the watchlist-membership filter (the row-level short-window + floor logic
is unchanged and reused). 404 when the ticker is unknown; `indicator: null` (or an
insufficient-history marker) when no snapshot exists.

- **Why a separate endpoint over embedding in `AssetDetailRead`?** (a) Keeps the
  technical-indicators capability self-contained and avoids bloating the assets detail
  schema with ~15 indicator fields + the floor. (b) The detail page can fetch and render
  the technical section independently, so a technical error/empty state does not block
  price/fundamentals rendering (app-shell requirement). (c) Mirrors the existing
  `/technical-indicators/*` read surface.
- **Why generalize the watchlist builder rather than add a new one?** The short-window
  subset, the floor, and the insufficient-history marker are already implemented and
  spec'd; the only change is dropping the membership filter for the single-asset path.
  Reusing it keeps the short-window profile identical across watchlist list and detail.
- Path choice `assets/{ticker}` (not `/{ticker}`) avoids colliding with the existing
  `config` / `watchlist` / `runs` segments on the router.

### D3 — Reuse the Assets list path for the watchlist table (thread `membership`)

Thread `membership` through `AssetsListParams` → `listAssets` → `useAssets` (the backend
already supports it). The watchlist table becomes a `useAssets({ membership: 'watchlist', ... })`
consumer with the same debounced search, `SortableHeader`, `MultiSelectDropdown`
category/sector filters, page-size persistence, and infinite-scroll sentinel as the
Assets page. The old `useWatchlist`/`listWatchlist` single-page fetch is no longer used
by the page.

- **Why not keep `useWatchlist`?** It is a fixed 100-row page with no controls; the table
  needs server-side search/sort/filter + paging, which `useAssets` already provides.
- `membership` is optional on `AssetsListParams`; omitting it preserves the Assets page's
  universe default (backend default `universe`), so the Assets page is untouched.
- The `localStorage` page-size key SHALL be watchlist-specific (e.g.
  `cadence.watchlist.pageSize`) so it does not clobber the Assets page preference.

### D4 — Extract shared fundamentals/technical rendering from the watchlist cards

The current `FundamentalsPanel` and `TechnicalPanel` (and the `INDICATOR_ROWS` /
`REVERSAL_FLAG_ROWS` / `formatCompactNumber` helpers) live inside `WatchlistPage.tsx`.
Extract them into shared components so the detail page renders fundamentals + technicals
identically, and the watchlist page drops its inline usage. This keeps one rendering of
each and preserves the existing insufficient-history copy/behavior already tested.

## Risks / Trade-offs

- **Two fetches on the detail page (details incl. fundamentals + per-asset technicals).**
  → Acceptable; independent sections, and it keeps a technical error from blocking the
  rest of the page (an explicit app-shell requirement). TanStack Query caches both.
- **Universe assets now show the short-window profile, not their full long-window set +
  trend gate.** → Intentional per the chosen scope (one read path, same for everyone);
  the detail view explicitly does not present the trend-gate verdict, and trading flows
  that use the full set are unchanged.
- **Dropping `useWatchlist` could leave a dead export.** → Remove it (and
  `listWatchlist`) if nothing else consumes it; otherwise leave it and note it. Verify
  with a usage search during apply.
- **Test DB column drift gotcha.** → Not applicable here (no new columns); but if the
  test DB lacks `technical_indicator.bar_count` from the prior change, reuse the
  non-destructive `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` approach rather than
  dropping the DB.
