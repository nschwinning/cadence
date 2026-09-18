## Context

See proposal.md — Why. Cadence already records daily EOD `SessionValueSnapshot`
rows per session, exposes a value-history read and a live-KPIs read on the session
detail page, and runs cron-guarded daily jobs (`snapshot-daily`, `reconcile-daily`)
triggered by a docker-compose `cron` sidecar that curls X-Cron-Token-guarded
endpoints on schedules from env vars. The `snapshot_all_sessions` service builds the
Pushover P&L report. `MarketDataProvider.fetch_history(ticker) -> list[HistoryBar]`
returns an ascending daily close series (yfinance-backed, injectable fake in tests).
The three-step add-nullable → backfill → set-NOT-NULL migration pattern is
established (`rebalance_prompt_version`).

## Goals / Non-Goals

**Goals:**
- A fixed, selectable catalog of benchmark indexes.
- System-owned daily benchmark price series, filled by a new cron job.
- Per-session benchmark selection (default S&P 500), switchable anytime in the UI.
- Benchmark comparison derived on read from the stored series (retroactive),
  surfaced on the chart, in KPI tiles, and in the daily Pushover report.

**Non-Goals:**
- No user-defined/custom benchmarks beyond the catalog.
- No CAPM alpha/beta, benchmark-relative Sharpe, or tracking-error — only the
  benchmark's return and the session's excess return (session% − benchmark%). See D12.
- No benchmarking of standalone portfolio views (session-scoped only).
- No intraday benchmark data (daily close only).

## Decisions

### D1. Fixed catalog as an enum with (id, display name, fetch symbol)
A `Benchmark` StrEnum (stable ids) in `paper_trading/constants.py`, each mapped to a
display name and a yfinance symbol:

| id | display name | symbol |
|----|--------------|--------|
| `SP500` | S&P 500 | `^GSPC` |
| `DJIA` | Dow Jones Industrial Average | `^DJI` |
| `NYSE_COMPOSITE` | NYSE Composite | `^NYA` |
| `NASDAQ_COMPOSITE` | Nasdaq Composite | `^IXIC` |
| `NASDAQ_100` | Nasdaq-100 | `^NDX` |
| `RUSSELL_2000` | Russell 2000 | `^RUT` |
| `SP100` | S&P 100 | `^OEX` |
| `WILSHIRE_5000` | Wilshire 5000 | `^FTW5000` |

Sessions store the **id**, never the raw symbol, so the symbol mapping can change
without touching stored data. A `GET /paper-trading/benchmarks` endpoint returns the
catalog for the UI. Default id = `SP500` via a new `DEFAULT_BENCHMARK` setting.

*Alternative considered:* free-form symbol (previous draft). Rejected per the user —
a curated, validated set with friendly names, and a known symbol set to fetch daily.

### D2. Stored benchmark price series, filled by a new cron job
New table `benchmark_prices(id PK, benchmark <enum str>, price_date Date, close Float,
created_at)` with unique `(benchmark, price_date)` + an index on `(benchmark,
price_date)`. A new cron-guarded endpoint `POST /ai-portfolio/fetch-benchmarks`
(X-Cron-Token) iterates the catalog, calls `fetch_history(symbol)`, and **upserts**
each returned daily bar. One benchmark's fetch failure is caught and skipped; others
proceed. This is the system-owned source of truth for comparisons.

*Alternative considered:* compute-on-read live fetch (previous draft). Rejected per
the user — they want a daily job that ingests and stores.

### D3. Retroactivity via full-history upsert
`fetch_history` returns the full daily history (`period="max"`). The ingestion upserts
the **entire returned series** (idempotent), so the first run backfills all history
needed to rebase sessions that started in the past, and later runs are cheap no-op
upserts except for the newest bar(s). This satisfies "retroactive for existing
sessions" without a separate backfill step.

*Trade-off:* the first ingestion writes many rows per benchmark (decades × 8 indexes).
Acceptable — one-time, and upserts are batched; the table stays small (daily grain).

### D4. Benchmark curve = buy-and-hold, rebased on read from stored prices
On a value-history / KPI read, load the session's stored benchmark closes, build a
sorted date→close map, and for each snapshot date `d` compute
`benchmark_value(d) = allocated_capital * close(d) / close(start)`, where `start` is
the session's first snapshot date and `close(·)` resolves to the **last stored close
on or before** that date (D5). Benchmark return fraction over the period =
`close(latest_snapshot_or_today)/close(start) - 1`; excess return =
session `total_return_pct − benchmark_return_fraction`. Nothing derived is stored.

### D5. Date-alignment rule
Benchmark closes exist only on trading days; snapshot dates may fall on non-trading
days (weekend crypto sessions, holidays). For a date `d`, use the last stored close on
or before `d`. If no stored close on/before `d` exists (e.g. before the series begins,
or the ingestion hasn't run yet), that point's benchmark value is null and the read
degrades gracefully (spec: null benchmark value / unavailable return, never an error).

### D6. Change-benchmark endpoint
`PUT /api/v1/paper-trading/sessions/{id}/benchmark` with body `{ "benchmark": <id> }`.
Service validates the id against the catalog (→ 422 via a domain error) and the session
exists (→ 404), sets `session.benchmark`, commits, returns the updated
`PaperTradingSessionRead`. Only the pointer changes; trades/positions/snapshots are
untouched, so subsequent reads recompute against the new series. Matches the app's
dedicated-action-endpoint style (archive/unarchive/close).

### D7. Pushover report includes benchmark comparison
`snapshot_all_sessions` already builds a per-session line and best/worst holding. Each
session line gains its benchmark return and excess return (e.g.
`name: $total (±$, ±%) | vs S&P 500 +2.1% (excess −0.4%)`). The comparison reuses the same
stored-series computation (D4). When unavailable, the line omits the benchmark suffix.
Ordering: the benchmark-ingestion cron is scheduled **before** the EOD snapshot cron so
the report has same-day closes; if it hasn't run, D5 degrades to the last stored close.

### D8. Session schema
Non-nullable `benchmark` column on `paper_trading_sessions`, `server_default` the
default id (`SP500`), backfilled to `SP500` for existing rows, via the three-step
migration. `create_session(...)` gains a required `benchmark` kwarg (build passes the
chosen/default id; test call sites pass `benchmark=Benchmark.SP500`).

### D9. API/schema shape
- `AIPortfolioBuildRequest`: `benchmark: Benchmark | None = None` (default applied in
  the service from `settings.DEFAULT_BENCHMARK`).
- `PaperTradingSessionRead`: `benchmark: str` (the id).
- Value-history item: `benchmark_value: float | None`.
- KPIs response: `benchmark: str`, `benchmark_return_pct: float | None`,
  `excess_return_pct: float | None`.
- Catalog response: list of `{ id, name }`.
- New settings: `DEFAULT_BENCHMARK: str = "SP500"`, `BENCHMARK_SCHEDULE` (cron sidecar).

### D11. Price-return indexes (dividends excluded), splits handled by the index
The catalog uses **price-return** index tickers (`^GSPC`, `^DJI`, …), which
**exclude dividends**. This is deliberate and fair: Cadence's session valuation
(`allocated + realized PnL − fees + mark-to-market`) does **not** credit dividend
cash to the portfolio, so comparing against a price-return index is apples-to-apples;
a total-return index (e.g. `^SP500TR`) would give the benchmark a dividend tailwind
the portfolio never receives and understate the strategy. Splits need no handling:
index providers adjust the index **divisor** on constituent splits, so the published
series is already continuous (no split jumps), and `close` is used directly.

*Alternative considered:* total-return variants. Rejected for now (asymmetry vs the
portfolio). Revisit only if the portfolio itself is later changed to credit dividends;
that would be a separate change and does not affect these specs.

### D12. Excess return now; CAPM alpha/beta is a documented follow-up
This change computes **excess return** (`session_total_return% − benchmark_return%`),
labelled exactly that — not "alpha." It is a single subtraction over figures already
derived (D4), always available once a benchmark return exists, and intuitive on a
dashboard. **Jensen's alpha and beta are explicitly out of scope here** and recorded as
a follow-up: beta = `cov(session_daily_returns, benchmark_daily_returns) /
var(benchmark_daily_returns)` estimated by regressing the session's daily NAV returns
(from snapshots) against the benchmark's daily returns (derivable from the stored
`benchmark_prices`), and alpha = `session_return − [risk_free + beta ×
(benchmark_return − risk_free)]`. That needs a minimum daily-return history (like the
Sharpe ratio) and additional compute/tests; a later change can add it as extra KPI
tiles/report figures **without altering these specs** (it only adds fields).

### D10. No extra caching layer
Because prices are now read from Postgres (D2), no in-process history cache is needed
(the earlier draft's cache existed only to avoid repeated yfinance calls on read). A
per-request date→close map is built from a single indexed query per session read.

## Risks / Trade-offs

- **[First ingestion writes large history]** → one-time, batched upserts, daily-grain
  table; subsequent runs are near-no-op. Could trim to a max lookback later without a
  spec change.
- **[yfinance TLS/offline failure for an index]** → D2 skips that benchmark; D5/read
  degrades to null; page renders value + KPIs without the benchmark line.
- **[Ingestion hasn't run yet on a given day]** → D5 uses the last stored close, so
  comparisons and the report degrade to the most recent available day rather than error.
- **[Crypto sessions trade on non-benchmark days]** → D5's "last close on or before"
  aligns every snapshot date to a valid stored close.
- **[Wilshire 5000 symbol availability on yfinance]** → `^FTW5000` chosen; if it 404s,
  D2 simply skips it (still selectable, shows "not yet available") — verify during apply
  and swap the symbol if a better one exists; symbol mapping is internal (D1).
- **[Existing test DB is create_all, not migrations]** → `benchmark` uses
  `server_default`; new `benchmark_prices` table is created by `create_all`; drop
  `cadence_test` once so the new column/table appear (known project pattern).

## Migration Plan

1. Add `benchmark` to the ORM model (`server_default="SP500"`) and the new
   `benchmark_prices` table.
2. Alembic migration (new head, down_revision = current head `d4b7e2f9a1c6`):
   create `benchmark_prices`; add `benchmark` nullable → `UPDATE ... SET
   benchmark='SP500' WHERE benchmark IS NULL` → set NOT NULL. Downgrade drops the
   column and the table.
3. Deploy is additive/backward-compatible; existing sessions read as S&P 500.
4. After deploy, run the benchmark-ingestion endpoint once (or wait for the cron) to
   backfill the price series; until then, benchmark figures read as "not yet
   available" and the UI/report degrade gracefully.
5. Rollback = downgrade (drops column + table); API fields become inert with no data
   loss to sessions/snapshots.

## Open Questions

None blocking. (Wilshire 5000's exact yfinance symbol is verified during apply per
the risk above; it does not change the specs, approach, or task breakdown.)
