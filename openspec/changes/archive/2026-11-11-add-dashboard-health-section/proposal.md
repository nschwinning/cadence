## Why

On 2026-11-10 the strategy-bot tick failed every 5 minutes for a whole trading day and nobody
noticed: tick outcomes are only returned to the cron sidecar and written to the backend log,
the dashboard's Automation panel covers AI rebalances only, and since per-bot isolation a single
failing bot no longer even fails the tick. Account inconsistencies (orphans, shortfalls, shorts,
unbooked orders) are likewise only visible on the Admin page. The dashboard should surface every
such problem without the operator having to open bot details or Admin.

## What Changes

- **Tick outcome log**: every bot tick records its outcome (time, market open, bots processed /
  skipped / failed, orders reconciled, or the error if the tick itself crashed). Outcomes older
  than **7 days** are pruned by the daily bot snapshot job.
- **Per-bot failure state**: a bot whose processing fails records when, the error, and how many
  ticks in a row have failed; the next successful tick clears it. The bot detail page shows a
  red banner while it is failing.
- **Tick health in the dashboard overview**: latest tick and counts, whether ticks are **stale**
  (market open and no tick for more than 15 minutes), and the failing bots.
- **Dashboard "Health" section** next to the Broker account tile: tick health (stale / crashed
  warnings, latest tick, failing bots with error and link) plus one-line **account consistency**
  counts (orphans, shortfalls, shorts, unresolved orders) linking to Admin, derived from the Admin
  account data the Broker account tile already loads.
- **Migration**: one table (`bot_tick_runs`) and three columns on `bot_sessions`. No new
  environment variables (retention and staleness thresholds are code-level settings with
  defaults).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: tick outcome log with 7-day retention; per-bot failure state cleared on
  success; failure banner on the bot detail view.
- `dashboard`: tick-health summary in the overview.
- `app-shell`: dashboard Health section.
- `order-journal`: an explicitly rejected order is handed to reconciliation immediately instead of
  blocking its symbol for the owner's whole lease (found while applying: otherwise a failing bot
  alternates between "failed" and "skipped" and its failure state flickers).

## Impact

- Backend: `strategy_bots/models.py` (`BotTickRun`, failure columns on `BotSession`), Alembic
  migration, `strategy_bots/service.py` (`run_tick` records outcomes and failures, prune in
  `run_bot_snapshots`), `api/routers/bots.py`, `config.py` (`BOT_TICK_RUN_RETENTION_DAYS=7`,
  `BOT_TICK_STALE_MINUTES=15`), `dashboard/service.py` + `api/schemas.py` (`tick_health`), bot
  read schema (failure fields).
- Frontend: `components/dashboard/HealthSection.tsx`, `DashboardPage.tsx`, bot detail banner,
  types.
- Out of scope: AI-rebalance and orchestrator-run failures (already in the Automation panel /
  orchestrator pages), push notifications for failures.
