## Why

A paper-trading session's PnL, total return, and Sharpe ratio are hard to
interpret in isolation: a +8% return means one thing in a flat market and the
opposite in a market that rose 20%. Users need to see each session's performance
**relative to a market benchmark index** (S&P 500, Nasdaq-100, Russell 2000, …)
to judge whether the AI strategy is actually adding value — on the session page
and in the daily push notification.

## What Changes

- Introduce a **fixed catalog of selectable benchmark indexes**: S&P 500, Dow
  Jones Industrial Average, NYSE Composite, Nasdaq Composite, Nasdaq-100,
  Russell 2000, S&P 100, and Wilshire 5000. Each maps to a market-data symbol the
  system knows how to fetch.
- A **new scheduled cron job** fetches the daily close of **every** catalog index
  and stores it in a benchmark price series, so the comparison data is owned by
  the system rather than fetched live per page view.
- Each paper-trading session **points at one benchmark index** (default S&P 500),
  chosen at build time and **changeable at any time from the session detail view**.
- A session's performance is compared against a **buy-and-hold of the same
  allocated capital** in its benchmark since the session's start date, derived on
  read from the stored price series (rebased to the session's start), so it works
  **retroactively** for existing sessions.
- The **value-history** read returns an aligned benchmark value per snapshot date;
  the **KPIs** read gains **benchmark return %** and **excess return** =
  session total-return % − benchmark return %.
- The **daily Pushover P&L report** includes each session's benchmark comparison
  (benchmark return and excess return) alongside its value and P&L.
- The frontend overlays a **benchmark line** on the session value chart, adds
  **KPI tiles** for benchmark return and excess return, offers the index selector
  on the build form, and lets the user **switch the benchmark** on the session
  detail page.

## Capabilities

### New Capabilities

<!-- None: this extends existing capabilities. -->

### Modified Capabilities

- `ai-paper-trading`: adds a fixed benchmark-index catalog; a scheduled
  cron-guarded ingestion of daily benchmark index closes into a stored price
  series; a benchmark selection persisted per session (default S&P 500) that can
  be changed at any time; benchmark value in the value-history read and benchmark
  return / excess return in the KPIs read, both derived from the stored series;
  and the daily P&L report includes each session's benchmark comparison.
- `app-shell`: the session detail view overlays the benchmark line on the value
  chart, shows benchmark-return and excess-return KPI tiles, and offers a control
  to switch the session's benchmark; the AI build form offers the index selector.

## Impact

- **Backend**
  - Schema: non-nullable `benchmark` column on `paper_trading_sessions` (default
    the S&P 500 catalog key, backfill existing rows); a new `benchmark_prices`
    table (benchmark key + date + close, unique per benchmark+date). New Alembic
    migration (new head).
  - New benchmark catalog (fixed enum of indexes → fetch symbols + display names)
    and a config setting for the default benchmark.
  - `paper_trading`: benchmark price ingestion + upsert; read-time benchmark
    computation (rebase stored closes to session start, align to snapshot dates);
    extended value-history and KPI reads; a service op to change a session's
    benchmark.
  - `ai_portfolio`: build flow captures/persists the chosen benchmark; the daily
    snapshot report includes benchmark return / excess return per session.
  - New cron-guarded endpoint to ingest benchmark prices; a session endpoint to
    change the benchmark; an endpoint to list the catalog for the UI. Value-history
    and KPI endpoints read the stored series.
  - `api/schemas.py`: build request gains a benchmark selection; value-history
    items and KPIs response gain benchmark fields; `PaperTradingSessionRead`
    exposes the benchmark; a benchmark-catalog response.
  - Ops: docker-compose cron sidecar gains a benchmark-ingestion job + schedule
    env, ordered before the EOD snapshot so the report has same-day closes.
- **Frontend**
  - `types/api.ts`: benchmark fields on the build request, value-history item,
    KPIs, and session types; a benchmark-catalog type.
  - Build form benchmark selector (default S&P 500); session detail benchmark
    switcher; chart benchmark overlay; benchmark and excess-return KPI tiles.
- **Dependencies**: none new — reuses yfinance via `MarketDataProvider`.
- **Out of scope**: benchmarking non-session (standalone portfolio) views;
  benchmark-relative Sharpe/beta/tracking-error; user-defined custom benchmarks
  beyond the fixed catalog.
