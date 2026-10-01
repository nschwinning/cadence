## Context

See `proposal.md` — Why. The Dashboard is currently a static count summary served by `GET /api/v1/dashboard/metrics` (`dashboard/service.get_dashboard_metrics`). Per-session performance already exists but only behind each session's detail page, computed on read from stored value snapshots via `paper_trading/service.py` (`list_value_history`, `session_kpis`, `compute_session_value`, `list_sessions_value_comparison`). AI run history across sessions is available via `ai_portfolio/service.list_ai_runs` / `get_inflight_rebalance_event`. The daily rebalance cron is `POST /api/v1/ai-portfolio/rebalance-daily`, guarded by `X-Cron-Token` (`api/routers/ai_portfolio.py`).

The one genuinely new capability is **stored price history**: the documented out-of-scope line ("price-history ingestion") is deliberately moved because best/worst universe performers over `1Y`/`Max` cannot be served by on-demand fetching. `MarketDataProvider` (`assets/market_data.py`) already has a `fetch_history(ticker) -> list[HistoryBar]` returning ascending daily bars — the building block for both backfill and daily append.

## Goals / Non-Goals

**Goals:**
- One range-scoped aggregate endpoint (`GET /api/v1/dashboard/overview`) that returns everything the rebuilt Dashboard needs, so the client fetches once per range and re-aggregates portfolio-selection changes locally.
- Store daily closes durably so per-asset market return is cheap to compute for any supported range.
- Keep the existing `/dashboard/metrics` endpoint and the Assets-page donut tiles untouched.

**Non-Goals:**
- No backtesting, no technical indicators, no intraday granularity (daily closes only).
- No dividend/total-return adjustment — returns are close-to-close price returns.
- No per-snapshot benchmark storage or new benchmark behavior (that is a separate, already-shipped concern).
- The equity curve stays `$`-only (no `%`/`$` toggle) and the balance summary stays range-independent.

## Decisions

### D1 — New `price_history` capability package, not a column on `assets`
A dedicated `price_history` package (`models.py` + `service.py`) with a `price_history` table (`asset_id` FK, `date`, `close`; unique `(asset_id, date)`, index on `asset_id, date`). A one-to-many time series does not belong inline on `assets`. Alembic migration with `down_revision` = the current head at implementation time (currently `f6a7b8c9d0e1`); keep a single linear head. **Alternative rejected:** reuse the existing `asset_daily_snapshot` table — it serves a different purpose (eligibility metric snapshots) and overloading it would couple unrelated lifecycles.

### D2 — Return via DB-resolved start point, per asset's own calendar
Per-asset range return is computed in `price_history/service.py` by resolving the range's start date against that asset's stored dates (first close on/after the computed start; YTD = first close of the current calendar year; Max = earliest stored close) and dividing the latest close by that start close − 1. Each asset uses only its own stored dates, so crypto (7-day) and equity calendars coexist without fabricated points. Assets lacking a resolvable start are excluded from performer rankings (never shown with a misleading value). **Alternative rejected:** a shared global trading calendar — brittle across mixed asset classes and needs holiday data we don't have.

### D3 — Ingestion piggybacks the existing cron, plus backfill on add
- **Backfill on add:** `assets/service.add_asset` (after successful persist) calls `price_history` ingestion to store the new asset's `fetch_history` closes, capped to a bounded lookback (~5y). Best-effort: a provider failure leaves the asset added with no history (mirrors the existing best-effort discovery pattern).
- **Daily append:** the `rebalance-daily` cron handler also triggers a price-history ingestion pass over all tracked assets, upserting closes not already stored. Per-asset failures are logged and skipped so the batch completes (same resilience contract as `reconcile-daily`). **Alternative rejected:** a brand-new cron endpoint — more cron wiring and secrets for no benefit; the 09:35/16:15 ET slots already align with "after close" ingestion.

### D4 — Provider gets a batch daily-close method
Add `fetch_daily_closes(tickers, start, end) -> dict[ticker, list[(date, close)]]` to the `MarketDataProvider` protocol (yfinance supports batch download; the stub returns deterministic synthetic closes). Backfill/daily ingestion call the batch form to avoid N sequential round-trips. `fetch_history` remains for the single-asset detail path. **Alternative rejected:** loop `fetch_history` per asset — works but is slow for daily ingestion across the whole universe.

### D5 — One `/overview` endpoint returns per-session series; client re-aggregates on selection
`dashboard/service.get_dashboard_overview(session, range)` returns per-session `{id, label, allocated_capital, current_value, pnl, fees, points:[{date, value}]}` (built from `list_value_history` windowed to the range + `session_kpis`/`compute_session_value`) plus `automation`, `recent_activity`, `universe_balance`, and `universe_performers`. The frontend sums the **selected** sessions' point series onto a common carry-forward date axis and recomputes the hero tiles + leaderboard locally — so toggling a portfolio never refetches. Money-weighted aggregation (Σpnl ÷ Σstart-value; Max vs Σallocated) is applied identically on server (defaults) and client (post-toggle). **Alternative rejected:** server-side re-aggregation per selection — a round-trip per checkbox click for data the client already holds.

### D6 — Range is a validated enum shared across the overview
A `DashboardRange` enum (`1D/1W/1M/YTD/1Y/Max`) in the dashboard capability is a required query parameter; an out-of-range value is rejected (422) rather than silently defaulted. The same enum resolves both the session-series window and the per-asset performer window, keeping their semantics identical.

### D7 — Automation next-run is an explicit approximation
The next-run time is derived arithmetically from the fixed 09:35/16:15 ET cron slots and flagged `approximate` in the payload; the UI labels it as such. We do not consult a market-holiday calendar (we have none) and the spec permits ignoring holidays.

## Risks / Trade-offs

- **[Backfill cost / rate limits on bulk add or first deploy]** → bounded lookback (~5y), batch `fetch_daily_closes`, best-effort per-asset so partial failure is tolerated; existing assets simply accumulate history from the first daily run if backfill is skipped.
- **[Price history empty on first deploy → performers section sparse]** → the performer ranking excludes assets without resolvable history and the UI shows a graceful empty/partial state until history accumulates; nothing else on the Dashboard depends on price history.
- **[Mixed asset calendars make a single x-axis for performers ambiguous]** → performers are a ranked list, not a time series, so each asset's return is computed on its own dates; only the equity curve shares a date axis and that is built from session value snapshots, not price history.
- **[Close-to-close return ignores dividends]** → accepted and documented as a simplification in the spec; acceptable for a paper-trading overview.
- **[Larger `/overview` payload than `/metrics`]** → scoped to active sessions and a capped activity list; per-session point series is the same data the session comparison chart already transfers, windowed to the range.
- **[Daily ingestion lengthens the cron handler]** → ingestion runs after the rebalance dispatch and is wrapped so its failure cannot abort rebalancing.

## Migration Plan

1. Add the `price_history` table via a new Alembic migration (single linear head off the current head). Deploy backend; `alembic upgrade head`.
2. On deploy there is no history yet. Either run a one-off backfill (reuse the ingestion pass) or let the daily cron accumulate history; the Dashboard degrades gracefully meanwhile.
3. Ship the `/overview` endpoint and the rebuilt Dashboard frontend together. `/metrics` and the Assets donuts are unchanged, so the Assets page is unaffected.
4. Rollback: revert the frontend to the prior Dashboard and downgrade the migration (drops `price_history`); no other table is altered.
