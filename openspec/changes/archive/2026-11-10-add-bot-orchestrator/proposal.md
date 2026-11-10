## Why

Strategy bots can only be created and stopped by hand today. The goal is an AI that runs
a portfolio of bots on its own: on a daily, weekly or monthly cadence it reads the market
and sector picture and decides which course-preset bots to deploy (on which tickers, with
how much capital) and which running bots to stop, inside limits the user sets. The preset
catalog and the Rolling-Average Reversion bot were built as the groundwork for this.

While researching, a contract violation surfaced: stopping a bot does **not** sell its
open positions. The session merely stops being ticked, leaving its shares unmanaged on the
shared Alpaca paper account, even though stopped bots are meant to be flat. An orchestrator
that stops bots depends on stops that actually exit, so this change fixes stopping for
every bot.

## What Changes

- **Stopping a bot sells its open positions**, for every stop path (manual, orchestrator).
  The session is marked stopped immediately; its remaining positions are sold at market by
  the next intraday tick while the market is open. Stop reasons gain `orchestrator`.
  **BREAKING (behaviour):** bots that were stopped before this change and still hold
  positions will have those positions sold on the first tick after deploy.
- **New "Orchestrators" area** (navigation entry, list, deploy form, detail page).
  Deploying an orchestrator sets:
  - capital pool (minimum $5,000);
  - maximum parallel bots (1–10, default 3);
  - maximum share of the pool per bot (default 50%), with every bot getting at least the
    $1,000 bot minimum;
  - maximum tickers per bot (1–10, default 5);
  - decision cadence (daily / weekly / monthly);
  - AI model and benchmark.
- **Capital pool that compounds.** Deploying a bot moves its allocation out of the
  orchestrator's free capital. When one of its bots is stopped and fully sold, the bot's
  final cash flows back to free capital. Allocated plus free never exceeds the pool's
  value, and the orchestrator's value is free capital plus its bots' current values.
- **Scheduled decision runs.** A weekday cron trigger at 09:00 ET, **before the market
  opens**, runs every orchestrator that is due for its cadence. The cadence uses the same due rules as AI
  portfolios, and only successful or partly successful runs count as done. A run:
  1. builds a market and sector briefing:
     - index technicals from stored benchmark closes;
     - per-sector breadth from the per-asset technical indicators;
     - per-sector news tone aggregated from per-ticker news sentiment;
     - a candidate table of eligible universe equities;
     - the preset catalog;
     - its running bots' performance;
     - its remaining limits;
  2. lets the AI (with a small budget of web searches for market and sector news) return
     a structured decision: a market summary, bots to stop with reasons, and bots to
     deploy (preset, tickers, capital, rationale);
  3. validates every action against the limits and the catalog, applies stops first and
     then deploys, and records rejected actions with reasons.
  A "Run now" button triggers a run outside the cadence. Runs skip on non-trading days
  (weekends and market holidays, read from the Alpaca market calendar). A run itself places
  no orders: its stops and deploys take effect at the first intraday tick after the
  market opens, so bots trade from the opening bell.
- **Decision audit.** Every run is persisted with its status (queued, running, succeeded,
  partial, failed, skipped), briefing, AI output, applied and rejected actions, web
  research, model, error and duration, and is shown on the orchestrator's detail page.
- **Stopping an orchestrator** stops (and sells) all of its active bots and ends its
  scheduling; archiving hides it once stopped.
- **Bot provenance.** Bots record the deploying orchestrator (origin `orchestrator`), and
  the bot detail page links back to it.
- Push notifications for scheduled runs (summary or failure), like AI rebalances.
- New tables `bot_orchestrators` and `bot_orchestrator_runs`; `bot_sessions` gains
  `orchestrator_id` and `capital_returned_at` (one migration).

## Capabilities

### New Capabilities

- `bot-orchestrator`: the AI bot orchestrator — configuration and limits, capital pool,
  scheduled and manual decision runs, decision briefing, decision validation and
  application, run audit, orchestrator lifecycle, notifications, and its views.

### Modified Capabilities

- `strategy-bots`: the session lifecycle (stopping sells open positions, the
  `orchestrator` stop reason and origin, the link to the deploying orchestrator); the
  drawdown kill-switch requirement's stop reasons; session provenance on the bot detail
  view (shows the deploying orchestrator).
- `app-shell`: adds the Orchestrators navigation entry.

## Impact

- **Backend**:
  - new `bot_orchestrator/` package (models, constants, service, briefing builder, agent,
    job runner);
  - `api/routers/bot_orchestrators.py` and `api/schemas.py`;
  - `strategy_bots/service.py`: selling stop, flatten pass in `run_tick`, capital return,
    `origin` / `orchestrator_id` on create;
  - `strategy_bots/constants.py`: `StopReason.ORCHESTRATOR`, `BotOrigin.ORCHESTRATOR`;
  - `config.py`: orchestrator timeout, turn and search budget settings;
  - one Alembic migration;
  - `docker-compose.yml`: cron line for `run-due` at 09:00 ET on weekdays;
  - `broker`: an `is_trading_day(day)` check (Alpaca market calendar; the stub returns
    true).
- **Frontend**:
  - `Sidebar.tsx` entry and icon, plus routes in `App.tsx`;
  - new `pages/orchestrators/` (list, deploy form, detail with bots and run history);
  - `api/orchestrators.ts` and types;
  - bot detail provenance.
- **Reused, not rebuilt**:
  - `rebalance_due`, the cron-token guard, the web-search tool and budget, `llm_trace`;
  - `compute_snapshot`, `resolve_sentiment_annotations`, the preset catalog and
    `create_bot_session`.
- **Out of scope**:
  - dedicated sector ETF or market-news feeds;
  - per-bot sizing chosen by the AI (bots use the default sizing);
  - the AI editing a running bot's parameters;
  - any AI-portfolio change;
  - crypto bots.
