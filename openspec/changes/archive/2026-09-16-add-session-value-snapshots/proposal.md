# Snapshot AI session portfolio value at end of day, chart it, and report daily P&L

## Why

A session's value today lives only in the broker account and the running
`total_pnl` — there is no persisted history, so we cannot chart how a portfolio
has performed over time, and nobody is told each day how their portfolios did.
Users want an equity curve per session and a daily push notification summarizing
the day's profit and loss.

## What Changes

- **Persist a daily value snapshot per active AI session.** Add a new
  `session_value_snapshots` table. A new synchronous cron endpoint
  `POST /api/v1/ai-portfolio/snapshot-daily` (guarded by the existing
  `X-Cron-Token`) fans out over **active AI sessions only**
  (`strategy_key == ai_buy_hold`, `status == active`) and records **one snapshot
  per session per day**. Re-running the same day is idempotent (upsert on
  `(session_id, snapshot_date)`) — no duplicate rows.
- **Value each session by mark-to-market equity accounting.** Read the session's open
  positions from its position ledger (see `add-session-position-ledger`), mark them to
  market via broker quotes, and compute
  `total_value = allocated_capital + realized total_pnl + unrealized P&L`. Store
  `total_value`, `cash_value`, `positions_value`, `daily_pnl`, `daily_pnl_pct`, and
  a per-position JSONB breakdown (ticker, quantity, price, market value, unrealized
  P&L, return). `daily_pnl` is measured against the prior snapshot, or against
  `allocated_capital` on the first snapshot.
- **Send a daily Pushover report.** After recording, the endpoint sends one report
  via the existing notifier: a per-session line (value + today's P&L, absolute and
  percent) plus the single best and worst individual holding ranked by return
  across all snapshotted sessions. Notifier failures never fail the job.
- **Expose value history for charting.** Add
  `GET /api/v1/paper-trading/sessions/{id}/value-history` returning the session's
  snapshots ascending by date.
- **Frontend: an equity-curve chart.** Add a dependency-free inline-SVG line chart
  (mirroring the existing `PriceSparkline` convention) of `total_value` over time
  on the paper-trading session page, plus its api module, types, and tests.
- **Schedule the job.** Add a second cron entry to the docker-compose `cron`
  sidecar (new `SNAPSHOT_SCHEDULE` env, default `15 16 * * 1-5` — just after the
  US equity close), curling the new endpoint with the shared cron token.

## Capabilities

### New Capabilities
<!-- none: this extends existing capabilities -->

### Modified Capabilities
- `ai-paper-trading`: ADD a requirement to snapshot each active AI session's
  portfolio value at end of day and send a daily P&L report; MODIFY "Read
  paper-trading session data" so a session's value history is readable.
- `app-shell`: ADD a requirement to render a session's portfolio-value line chart.

## Impact

- Affected specs: `ai-paper-trading` — ADDED "Snapshot session portfolio value at
  end of day", MODIFIED "Read paper-trading session data" (value history is
  readable). `app-shell` — ADDED "Session value history chart".
- Depends on `add-session-position-ledger` (ships first): valuation reads the session's
  open positions from the ledger, not the broker-account intersection.
- Affected code (backend, schema): Alembic migration (`down_revision` = the
  `add-session-position-ledger` migration head, chaining after it) creating
  `session_value_snapshots` (UUID PK, `session_id` FK `ON DELETE CASCADE`,
  `snapshot_date`, the value/pnl floats, `positions` JSONB, `created_at`) with a unique
  constraint on `(session_id, snapshot_date)`; matching ORM model in
  `paper_trading/models.py`.
- Affected code (backend, behavior): `paper_trading/service.py` (compute a session's
  mark-to-market value from its ledger positions + broker quotes;
  `record_value_snapshot` upsert;
  `list_value_snapshots` read); `ai_portfolio/service.py` (orchestrate the daily
  fan-out over active AI sessions, build the Pushover report with best/worst holding,
  send via the safe notifier wrapper); `api/routers/ai_portfolio.py` (new
  `POST /snapshot-daily`, guarded by `require_valid_cron_token`);
  `api/routers/paper_trading.py` (new `GET /sessions/{id}/value-history`);
  `api/schemas.py` (snapshot read model + value-history list response + snapshot-run
  response). No new setting — reuses `REBALANCE_CRON_TOKEN`.
- Affected code (frontend): `api/paperTrading.ts` (fetcher, query key,
  `useSessionValueHistory`); `types/api.ts` (`SessionValueSnapshot` + list response);
  new `pages/paper-trading/SessionValueChart.tsx` rendered on
  `PaperTradingSessionPage.tsx`, with co-located tests.
- Affected code (ops): `docker-compose.yml` `cron` sidecar gains a `SNAPSHOT_SCHEDULE`
  env and a second generated script + crontab line; `.env.example` documents it.
- Tests: valuation math; snapshot idempotency (re-run upserts, no duplicate);
  fan-out targets only active AI sessions; `daily_pnl` baseline (first vs subsequent);
  report content (per-session lines + best/worst holding); notifier-failure isolation;
  403 on bad/missing cron token; the read endpoint; frontend chart render + empty
  state + the api hook.
- Backwards compatibility: purely additive — a new table and new endpoints; existing
  sessions simply have no snapshots until the job first runs. Sessions with no ledger
  positions record an all-cash snapshot (`positions_value = 0`).
