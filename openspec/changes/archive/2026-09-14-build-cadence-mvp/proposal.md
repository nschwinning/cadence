## Why

Cadence needs its first working feature set: a user should be able to build a universe of assets, let an AI recommend which to add, have an AI assemble a paper-trading portfolio on Alpaca, and have that portfolio automatically rebalanced every trading day. The scaffold (health-only app, DB, Docker, `.claude`/OpenSpec tooling) already exists; this change delivers the end-to-end product on top of it by porting the proven asset-management + recommender capabilities from the sibling `quantara` project and the Alpaca AI paper-trading + daily-rebalancing capabilities from the sibling `trading-bot` project, re-implemented in Cadence's layered conventions.

## What Changes

- **Assets**: add an asset by ticker (yfinance market data + EUR eligibility evaluation), list with pagination/search/sort/filter, view once-per-day detail snapshot, delete.
- **AI recommender**: a queued background run where an OpenAI agent (with SerpAPI web search) proposes candidate tickers; eligible ones are added via the asset service. An offline stub runs without API keys (`RECOMMENDER_STUB`).
- **Portfolios**: persist AI-managed portfolios (name, stocks, risk profile, allocation cap, source).
- **AI paper trading**: an Alpaca broker integration (paper/live + base URLs config-driven; `ALPACA_STUB` fake for offline/tests) behind a `Broker` Protocol; an AI agent builds a target portfolio and allocations; an executor turns allocations into Alpaca orders; a paper-trading session records trades, runs, and closed positions; build/rebalance runs are audited as AI-portfolio events. POST endpoints queue work and return immediately; clients poll for status.
- **Daily rebalancing**: a rebalance run where the AI evaluates current holdings (hold/sell/cover) and proposes new positions, and the executor applies the deltas; a cron-triggered `POST /api/v1/ai-portfolio/rebalance-daily` endpoint (guarded by `X-Cron-Token`) fans out to every active session marked for daily rebalancing. A Docker cron sidecar fires it on trading days.
- **Dashboard**: aggregated metrics across assets, portfolios, and paper-trading sessions.
- **App shell**: React shell (header/sidebar/layout) and navigation across Dashboard, Assets, Asset detail, Portfolios, and Paper Trading; typed API clients and polling hooks for run/event status.

## Capabilities

### New Capabilities
- `assets`: Add/list/detail/delete tradeable assets sourced from yfinance, with EUR-based eligibility evaluation and a once-per-day detail snapshot.
- `asset-recommendations`: Queued, pollable AI recommendation runs that propose and add eligible assets; offline stub mode.
- `portfolios`: Persistence and retrieval of AI-managed portfolios (stocks, risk profile, allocation cap, source).
- `ai-paper-trading`: Alpaca-backed AI portfolio build and paper-trade execution (broker abstraction, executor, sessions, trades, runs, closed positions, AI-portfolio events).
- `daily-rebalancing`: AI-driven daily rebalance of active sessions and the cron-guarded trigger that fans out to all sessions enrolled in daily rebalancing.
- `dashboard`: Aggregated metrics across assets, portfolios, and sessions.
- `app-shell`: Frontend application shell and navigation across all pages, with typed API clients and polling for asynchronous runs.

### Modified Capabilities
<!-- None: this is a greenfield build; no existing specs change. -->

## Impact

- **New backend packages** under `backend/src/cadence/`: `assets/`, `recommendations/`, `portfolios/`, `broker/`, `paper_trading/`, `ai_portfolio/`, `dashboard/`, plus new routers wired into `api/app.py` and schemas in `api/schemas.py`.
- **Database**: new Alembic migrations for `assets`, `asset_daily_snapshot`, `recommendation_run`, `portfolios`, `paper_trading_sessions`, `paper_trades`, `session_runs`, `closed_positions`, `ai_portfolio_events`. Alembic remains the source of truth; `migrations/env.py` imports the new models.
- **Dependencies**: adds `requests` (Alpaca REST); reuses existing `yfinance`, `openai-agents`, `serpapi`, `truststore`.
- **APIs**: new resource routers under `/api/v1` (`/assets`, `/recommendations`, `/portfolios`, `/ai-portfolio`, `/paper-trading`, `/dashboard`); one cron-guarded endpoint (`/ai-portfolio/rebalance-daily`).
- **Config**: consumes `OPENAI_API_KEY`, `SERP_API_KEY`, `RECOMMENDER_MODEL`, `RECOMMENDER_STUB`, `AI_PORTFOLIO_MODEL`, `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER`, `ALPACA_STUB`, `REBALANCE_CRON_TOKEN` (all already defined in `config.py`).
- **Ops**: the Docker `cron` sidecar (already scaffolded) begins hitting the rebalance endpoint on trading days once this change lands.
- **Frontend**: new pages, typed API clients, and navigation entries; existing skeleton shell is extended.
- **Out of scope**: technical indicators, price-history ingestion, backtesting, Interactive Brokers, multi-agent stock discovery.
