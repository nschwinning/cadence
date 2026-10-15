## 1. Asset membership + universe isolation

- [x] 1.1 Add an `AssetMembership` str enum (`UNIVERSE`, `WATCHLIST`) in
  `assets/category.py` (or a sibling constants module) and a non-nullable
  `membership` column (default `UNIVERSE`, indexed) to `Asset` in
  `assets/models.py`.
- [x] 1.2 Add `membership: AssetMembership | None = AssetMembership.UNIVERSE`
  to `list_assets` and `count_assets` in `assets/service.py` (filter when set;
  `None` = all memberships) and filter `get_universe_assets` to `UNIVERSE`.
- [x] 1.3 Point the recommender exclusion at all assets:
  `recommendations/service.py` builds `exclude_tickers` with
  `list_assets(session, membership=None)`.
- [x] 1.4 Alembic migration (`down_revision = "e1f2a3b4c5d6"`) adding
  `assets.membership` with `server_default='universe'`, backfilling existing
  rows, keeping it NOT NULL + indexed; round-trip (`upgrade`/`downgrade`) and
  `alembic check` clean.
- [x] 1.5 Tests: `list_assets()`/`get_universe_assets()` default excludes
  watchlist rows; `membership="watchlist"`/`membership=None` filters; a watchlist
  asset is absent from build/rebalance candidate reads but readable by id/ticker.

## 2. SEC EDGAR fundamentals provider + storage

- [x] 2.1 New `asset_fundamentals` table (1:1 `asset_id` FK cascade, JSONB
  `document`, `source`/`status`, `fetched_at`) in `assets/models.py`; include it
  in the migration from 1.4 (or a sibling migration in the same chain).
- [x] 2.2 Define a `FundamentalsProvider` protocol + raw `Fundamentals`
  dataclass (revenue, gross/operating/net margin inputs, operating cash flow,
  earnings/EPS, company details) in `assets/market_data.py` (or a new
  `assets/fundamentals.py`), keeping the seam sync + fakeable.
- [x] 2.3 Implement `SecEdgarFundamentalsProvider` confining HTTP to EDGAR
  (`company_tickers.json` ticker→CIK, `companyfacts` XBRL), reading a descriptive
  `User-Agent` from `config.py` (new setting); map facts → `Fundamentals`.
- [x] 2.4 Service helper `record_fundamentals(session, asset, provider)` —
  best-effort fetch + persist; unresolved CIK / no facts / network error →
  persist `status=unavailable` and never raise.
- [x] 2.5 Tests (fake provider, no network): facts mapped + persisted; missing
  CIK → `unavailable`; provider error → `unavailable` and asset intact.

## 3. Watchlist recommendation run

- [x] 3.1 Add `target` (`universe` default / `watchlist`) to `RecommendationRun`
  (`recommendations/models.py`) and to the migration chain (default `universe`,
  backfill, NOT NULL).
- [x] 3.2 Queue request schema + router (`api/routers/recommendations.py`): accept
  an optional target; reject a `watchlist` target with any non-stock category
  (422); echo target on the run read schema.
- [x] 3.3 Emerging-companies prompt builder in `recommendations/agent.py`
  (explicitly seek emerging companies from promising sectors; keep US-stock scope
  + the all-assets exclusion list), selected when target is watchlist.
- [x] 3.4 Branch the execution path (`recommendations/service.py` +
  `recommendations/background.py`) on target: a watchlist candidate is added as a
  `WATCHLIST` member via the shared fetch/tradability path WITHOUT maturity
  rejection, deduped against all assets, then `record_fundamentals` runs; record
  per-candidate outcomes; stop at requested count.
- [x] 3.5 Thread the `FundamentalsProvider` (and existing broker/market provider)
  through `background.py`/`service.py` like the other seams.
- [x] 3.6 Tests: watchlist run adds an emerging ineligible stock as a watchlist
  member with fundamentals; rejects untradable/non-stock; skips an existing
  ticker; queue rejects watchlist+crypto; universe run behavior unchanged.

## 4. API read surface

- [x] 4.1 `AssetRead` (+ any list/read schema) exposes `membership`; add a
  fundamentals read schema/field and a way for the watchlist view to read entries
  with fundamentals (list filter `membership=watchlist`, fundamentals included or
  via the asset-detail read).
- [x] 4.2 Assets list router passes membership through (default universe) and the
  watchlist listing uses `membership=watchlist`.
- [x] 4.3 Tests: schema exposes `membership` + fundamentals; list router honors
  the membership filter and its count.

## 5. Frontend Watchlist page

- [x] 5.1 Add a Watchlist sidebar/nav entry and route in the app shell.
- [x] 5.2 Watchlist page: trigger a watchlist-targeted recommendation run reusing
  the AI-run polling hook; show in-progress → terminal outcome.
- [x] 5.3 List watchlist entries with their fundamentals (revenue, margins, cash
  flow, earnings, company details), indicating entries whose fundamentals are
  unavailable; surface API errors.
- [x] 5.4 Client types for `membership` + fundamentals; vitest coverage for the
  page (trigger, list render, unavailable-fundamentals state).

## 6. Verification

- [x] 6.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 6.2 Migration round-trip (`uv run alembic upgrade head` → `downgrade base`)
  and `uv run alembic check` (no drift).
- [x] 6.3 Frontend: `npm run typecheck && npx vitest run && npm run build`.
