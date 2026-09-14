## 1. Brokerage abstraction (foundation)

- [x] 1.1 Add `broker/models.py` with `Order`/`Position`/`AccountInfo`/`Quote` and the `OrderSide`/`OrderType`/`OrderStatus`/`TimeInForce` enums (ported from trading-bot). Verify: `uv run python -c "from cadence.broker import models"` imports cleanly.
- [x] 1.2 Add `broker/base.py` with a `@runtime_checkable Broker` Protocol (account info, positions, quote(s), submit/cancel/get order, open orders, `is_market_open`, buy/sell helpers) and `BrokerError`/`OrderError`/`ConnectionError`. Verify: a unit test asserts `StubBroker` satisfies `isinstance(..., Broker)`.
- [x] 1.3 Add `broker/alpaca.py` (`AlpacaBroker`, `requests`-based) reading `settings.ALPACA_API_KEY/SECRET_KEY` and selecting paper vs live base URL from `settings.ALPACA_PAPER`; raise a clear error when credentials are missing. Verify: unit test with a mocked `requests` session maps a submitted order and reads the clock/market-open.
- [x] 1.4 Add `broker/stub.py` (`StubBroker`) — deterministic in-memory account, positions, quotes, order fills, always-open clock. Verify: unit tests cover buy/sell updating positions and account.
- [x] 1.5 Add a `get_broker()` dependency factory selecting `StubBroker` when `settings.ALPACA_STUB` else `AlpacaBroker`. Verify: overriding it in a test client swaps the implementation.

## 2. Assets (port from quantara)

- [x] 2.1 Port `assets/` (`models.py`, `constants.py`, `errors.py`, `market_data.py` with `MarketDataProvider` Protocol + `YFinanceMarketDataProvider`, `category.py`, `sector.py`, `metrics.py`, `evaluation.py`, `service.py`), dropping price-bar/price-history helpers; keep the daily snapshot. Verify: `uv run python -c "from cadence.assets import service, models"` imports.
- [x] 2.2 Add the `assets` + `asset_daily_snapshot` ORM models and an Alembic migration; import them in `migrations/env.py`. Verify: `uv run alembic upgrade head` then `downgrade base` round-trips cleanly against the test DB.
- [x] 2.3 Add asset Pydantic schemas to `api/schemas.py` and the thin `api/routers/assets.py` (POST/GET list/GET detail/DELETE), mapping domain errors to 409/422/503/404. Remove any `/{ticker}/technical-indicators` route. Verify: pytest covers add (201), duplicate (409), unknown (422), list filter/sort, detail (200/404) using a fake provider.
- [x] 2.4 Wire the assets router into `create_app()`. Verify: `GET /api/v1/assets` returns 200 from the TestClient.

## 3. Asset recommendations (port from quantara)

- [x] 3.1 Port `recommendations/` (`agent.py` with `RecommenderAgent` Protocol + `OpenAIRecommenderAgent`, `stub.py`, `composition.py`, `constants.py`, `errors.py`, `models.py`, `service.py`, `background.py`). Verify: imports cleanly.
- [x] 3.2 Add the `recommendation_run` ORM model + Alembic migration; import in `env.py`. Verify: migration round-trips.
- [x] 3.3 Add recommendation schemas + `api/routers/recommendations.py` (POST 202, GET list, GET detail with dead-worker reaping) and `get_recommender_agent()`/`get_job_runner()` factories. Verify: pytest with `RECOMMENDER_STUB` drives a run queued→completed and asserts eligible candidates are added; unknown run → 404.
- [x] 3.4 Register the recommender orphan-run reaper in the app lifespan and wire the router. Verify: a non-terminal run created before startup is marked failed after `create_app()` lifespan runs.

## 4. Portfolios

- [x] 4.1 Add `portfolios/` (`models.py` ORM, `constants.py` source/risk-profile enums, `errors.py`, `service.py` create/list/get/update-stocks with ticker normalization and validation). Verify: imports cleanly.
- [x] 4.2 Add the `portfolios` Alembic migration; import model in `env.py`. Verify: migration round-trips.
- [x] 4.3 Add portfolio schemas + `api/routers/portfolios.py` (POST/GET list/GET by id) and wire it. Verify: pytest covers create (valid + empty-ticker rejection), list, get (200/404).

## 5. Paper-trading persistence

- [x] 5.1 Add `paper_trading/` (`models.py` for `paper_trading_sessions`/`paper_trades`/`session_runs`/`closed_positions` with a `ScheduleMode` enum, `constants.py`, `errors.py`, `service.py` — create/get/list sessions, record trade/run/closed-position, update session last-run/status). Verify: imports cleanly.
- [x] 5.2 Add the Alembic migration for all four tables; import models in `env.py`. Verify: migration round-trips; unique `(portfolio_id, strategy_key)` enforced by a test.
- [x] 5.3 Add paper-trading read schemas + `api/routers/paper_trading.py` (list sessions, get trades/runs/positions) and wire it. Verify: pytest reads back a seeded session's trades/runs/positions.

## 6. AI portfolio build & execution

- [x] 6.1 Add `ai_portfolio/agent.py` — the structured Pydantic output models (build + rebalance results and nested types) and sync `build_ai_portfolio`/`rebalance_ai_portfolio` wrapping the async SDK with timeouts, using `build_agent(output_type=..., tools=[web_search])` and `settings.AI_PORTFOLIO_MODEL`. Verify: a fake-agent unit test returns a valid `AIPortfolioBuildResult`.
- [x] 6.2 Add `ai_portfolio/executor.py` (`AIPortfolioExecutor.execute_build`/`execute_rebalance`) — allocation normalization, per-position sizing from quotes/buying power, skip sub-one-share, close-before-open, per-ticker try/except → `TradeResult`. Verify: unit tests against `StubBroker` cover build sizing and a rebalance that closes then opens.
- [x] 6.3 Add the `ai_portfolio_events` ORM model + Alembic migration; import in `env.py`. Verify: migration round-trips.
- [x] 6.4 Add `ai_portfolio/service.py` + `ai_portfolio/background.py` — the build job flow (agent → create portfolio + session → execute → record trades/run/event) and its single-worker runner. Verify: pytest with `ALPACA_STUB` + fake agent runs a build end to end and asserts a portfolio, session, trades, run, and a succeeded build event exist.
- [x] 6.5 Add AI-portfolio schemas + `api/routers/ai_portfolio.py` build endpoints (`POST /build`, `GET /build/status/{event_id}`, `GET /sessions/{id}/events`) and wire it; register the AI-event orphan reaper in the lifespan. Verify: pytest queues a build (returns event id) and polls status to a terminal state.

## 7. Daily rebalancing

- [x] 7.1 Extend `ai_portfolio/service.py`/`background.py` with the rebalance job flow (read positions + account, assemble candidates, agent evaluate, execute deltas, record trades/closed-positions/run/event), guarded by `broker.is_market_open()` (record `skipped` when closed). Verify: pytest with `StubBroker` open vs closed asserts orders placed vs run recorded skipped.
- [x] 7.2 Add `POST /ai-portfolio/sessions/{id}/rebalance` (validates active AI session, skips if already running) and the enrollment flag on build. Verify: pytest covers rebalance of an enrolled session and rejection of a non-eligible session.
- [x] 7.3 Add `POST /ai-portfolio/rebalance-daily` guarded by `X-Cron-Token` (`settings.REBALANCE_CRON_TOKEN`, empty rejects all), fanning out to active enrolled sessions and skipping already-running ones. Verify: pytest asserts valid token triggers enrolled sessions and returns triggered/skipped ids; missing/incorrect/empty-config token → rejected.
- [x] 7.4 Confirm the Docker `cron` sidecar targets the endpoint with the token. Verify: `docker compose config` shows the cron service posting to `/api/v1/ai-portfolio/rebalance-daily` with `X-Cron-Token`.

## 8. Dashboard

- [x] 8.1 Add `dashboard/` (`service.py` aggregating asset composition/counts, portfolio count, active-session and recent-trade counts) + schema + `api/routers/dashboard.py`, wired in. Verify: pytest asserts zeroed metrics on an empty DB and correct counts after seeding.

## 9. Frontend

- [x] 9.1 Add typed API clients under `frontend/src/api/` (`assets`, `recommendations`, `portfolios`, `aiPortfolio`, `paperTrading`, `dashboard`) with key factories, raw fns, and TanStack hooks (polling hooks for runs/events) and mirror types in `types/api.ts`. Verify: `npm run typecheck` passes; Vitest covers a client's key factory/serialization.
- [x] 9.2 Add pages — Dashboard (metrics), Assets (list + add + filters), Asset detail, Portfolios (list + detail), Paper Trading (sessions + session detail with trades/runs/positions/events) — and expand Sidebar nav to all views. Verify: Vitest render tests for each page against mocked hooks; `npm run test` passes.
- [x] 9.3 Wire AI actions in the UI (start recommendation run, build AI portfolio, trigger rebalance) with in-progress → terminal polling feedback. Verify: a Vitest test drives a mocked run from running to completed and asserts the UI updates.

## 10. End-to-end verification

- [x] 10.1 Run the full backend suite and migration round-trip. Verify: `cd backend && uv run pytest` green and `uv run alembic upgrade head`/`downgrade base` clean.
- [~] 10.2 Boot the stack (`docker compose up --build`) and smoke test with stubs: `GET :8002/health` ok; add an asset; run a recommendation (`RECOMMENDER_STUB=true`); build an AI portfolio (`ALPACA_STUB=true`); call `rebalance-daily` with the token; confirm rows in `assets`, `recommendation_run`, `portfolios`, `paper_trading_sessions`, `paper_trades`, `session_runs`, `ai_portfolio_events`; frontend reachable at `:5174`.
  - DONE offline: all 4 containers boot healthy; `GET /health` ok (DB connected); migrations auto-applied on boot (all 10 tables, head `de5a2bf36170`); frontend reachable at `:5174`; `rebalance-daily` cron-token guard verified (missing/wrong → 403, correct → 200 fan-out); recommendations/dashboard endpoints 200. Fixed a compose bug: the container `DATABASE_URL` was being overridden by the host `.env` (localhost:5435) via Compose interpolation → pinned to `db:5432`.
  - BLOCKED by environment/credentials (not code): in-container yfinance (asset add, recommendation enrichment) fails with `CertificateVerifyError` under corporate TLS interception — the live asset path was instead verified on the HOST (fetched AAPL info + 11,529 history bars via truststore/OS trust). The AI-portfolio build/rebalance row population needs an `OPENAI_API_KEY` (no AI-agent stub exists — design scoped stubs to recommender+broker); the full build→rebalance flow is covered by the 233 backend tests using `FakeAIPortfolioAgent` + `StubBroker`. To exercise these live, run the backend on the host with real keys (see 10.3), or add an optional `AI_PORTFOLIO_STUB`.
- [ ] 10.3 (Optional, needs real paper keys) Set `ALPACA_STUB=false`, `ALPACA_PAPER=true` and run one build against `paper-api.alpaca.markets`. Verify: orders appear in the Alpaca paper account and trades are recorded. — NOT RUN: requires user-supplied `OPENAI_API_KEY` + `ALPACA_API_KEY`/`ALPACA_SECRET_KEY` and a non-intercepted network (host run).
