## 1. Price-history capability (schema + storage)

- [x] 1.1 Create `price_history` package with `models.py` defining the `PriceHistory` ORM (`asset_id` FK → assets, `date`, `close`), unique `(asset_id, date)` and index on `(asset_id, date)`; verify `uv run mypy src/cadence` passes and the model imports.
- [x] 1.2 Add an Alembic migration creating the `price_history` table with the unique constraint + index, `down_revision` = current head; verify `uv run alembic upgrade head` then `downgrade -1` round-trips and `uv run alembic check` reports no drift.
- [x] 1.3 Implement `price_history/service.py` upsert (`store_closes(session, asset_id, [(date, close)])`) that inserts new dates and overwrites an existing date's close; verify a unit test that ingesting the same date twice leaves one row with the latest close.
- [x] 1.4 Implement `price_history/service.asset_return(session, asset_id, range)` resolving the per-asset start date (first close ≥ range start; YTD = first close of current calendar year; Max = earliest stored close) and returning close-to-close return, or `None` when no start can be resolved; verify unit tests for a fixed range, YTD, Max, and insufficient-history → `None`.

## 2. Market-data provider batch method

- [x] 2.1 Add `fetch_daily_closes(tickers, start, end) -> dict[str, list[tuple[date, float]]]` to the `MarketDataProvider` Protocol and implement it in the yfinance provider (batch download); verify `mypy` passes and a provider-level test (mocked/stub) returns ascending closes per ticker.
- [x] 2.2 Implement `fetch_daily_closes` in the stub provider returning deterministic synthetic closes so offline/test mode works; verify a unit test asserts stable, per-ticker series.

## 3. Ingestion wiring

- [x] 3.1 Implement an ingestion pass in `price_history/service.py` (`ingest_latest(session, provider, assets)` and `backfill(session, provider, asset, lookback)`) that is idempotent and best-effort per asset (one asset's provider failure is logged and skipped); verify a unit test where one asset raises still stores the others.
- [x] 3.2 Call backfill from `assets/service.add_asset` after successful persist (bounded ~5y lookback), best-effort so a provider failure leaves the asset added with no history; verify a test that a successful add stores closes and that a backfill failure still returns the added asset.
- [x] 3.3 Trigger the daily ingestion pass from the `rebalance-daily` cron handler after rebalance dispatch, wrapped so ingestion failure cannot abort rebalancing; verify a test that hitting the cron endpoint ingests closes and that an ingestion error does not change the rebalance response.

## 4. Dashboard overview — backend

- [x] 4.1 Add a `DashboardRange` enum (`1D/1W/1M/YTD/1Y/Max`) and range→start-date resolution helper in the dashboard capability; verify unit tests for each range's resolved window (including YTD and Max).
- [x] 4.2 Implement `dashboard/service.get_dashboard_overview(session, range)` returning per active session `{id, label, allocated_capital, current_value, pnl, fees, points:[{date, value}]}` (reusing `list_value_history` windowed to the range, `session_kpis`, `compute_session_value`); verify a unit test over seeded active sessions returns range-windowed series and range-relative pnl/fees, and that sessions with no value before the range start carry zero.
- [x] 4.3 Extend the overview with the automation summary (latest rebalance run + status/time, in-flight flag, failed-run count within range, approximate next run from the 09:35/16:15 ET slots flagged `approximate`) using `list_ai_runs` / `get_inflight_rebalance_event`; verify a unit test asserts each field including the failed-run count honoring the range.
- [x] 4.4 Extend the overview with recent activity (build/rebalance/close runs within the range, newest first, capped) and the universe section (range-independent balance summary: eligible/ineligible, sectors covered, top-sector & top-category share; plus best/worst performers via `price_history.asset_return`, small fixed count, excluding assets with no return); verify unit tests for the capped/ordered feed, the balance summary, and best/worst ranking with an insufficient-history asset excluded.
- [x] 4.5 Add Pydantic schemas in `api/schemas.py` and the `GET /api/v1/dashboard/overview` route (range query param, 422 on unsupported range), leaving `/dashboard/metrics` unchanged; verify an API test returns the overview for a valid range and 422 for an invalid one.
- [x] 4.6 Run `uv run ruff check . && uv run mypy src/cadence && uv run pytest` and verify the full backend suite is green.

## 5. Dashboard overview — frontend

- [x] 5.1 Mirror the overview response in `types/api.ts` and add a typed `dashboard` client hook (`useDashboardOverview(range)`) keyed by range; verify `npm run typecheck` passes.
- [x] 5.2 Add the global range selector control (`1D/1W/1M/YTD/1Y/Max`, one active) driving a dashboard-level range state; verify a Vitest test that selecting a range refetches/keys the overview for that range.
- [x] 5.3 Build the combined equity curve as a dependency-free inline-SVG line summing the selected sessions on a carry-forward common date axis, with a checkbox/legend of active sessions (all selected by default) and an empty state when none selected; verify Vitest tests for the summed line, toggling a session, and the empty state.
- [x] 5.4 Build the hero performance tiles (total value, range P&L $, money-weighted range return %, range fees) recomputed client-side from the selected sessions; verify a Vitest test that tiles reflect range and selection changes without a refetch.
- [x] 5.5 Build the portfolio leaderboard table sorted by range return desc, columns name/value/P&L/return/fees with row links to `/paper-trading/:id` and up/down coloring, honoring the selection; verify a Vitest test for sort order, row link, and that deselecting removes a row.
- [x] 5.6 Build the automation panel (latest run + link, in-flight indicator, range failed-run count, approximate next run) and the recent-activity feed (capped, newest first, run links); verify Vitest tests rendering each from fixture data.
- [x] 5.7 Build the universe section (range-independent balance summary + range-driven best/worst performers); verify a Vitest test that the balance summary is stable across range changes while performers update.
- [x] 5.8 Assemble the rebuilt `DashboardPage` composing all sections under the global range selector (keeping existing nav/shell), and update `DashboardPage.test.tsx`; verify `npm run typecheck && npx vitest run && npm run build` all pass.

## 6. Validation

- [x] 6.1 Run `openspec validate enrich-dashboard-overview --strict` and verify it passes.
