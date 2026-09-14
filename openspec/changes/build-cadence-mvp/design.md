## Context

See `proposal.md` — Why. The scaffold already provides the FastAPI app factory (health-only), sync SQLAlchemy 2.0 + Alembic, pydantic-settings `settings` (with all Alpaca/rebalance keys), the `agents/` wrapper (`build_agent` + `web_search`), Docker Compose (db/backend/frontend/cron), and the React shell. This change fills in the domain packages behind that shell. Two proven sources are being re-implemented into Cadence's conventions: asset management + recommender (from `quantara`, which already uses these exact conventions) and Alpaca AI paper trading + daily rebalancing (from `trading-bot`, which uses raw psycopg, lazy table creation, hardcoded Alpaca URLs, and module-level thread pools — all of which must be adapted).

## Goals / Non-Goals

**Goals:**
- Re-implement the ported behavior in Cadence's layered module conventions (models/service/errors/constants/background; thin routers; Protocol-wrapped I/O with stubs).
- Make schema Alembic-owned (one migration per capability), not created at runtime.
- Make brokerage paper/live selection and endpoints configuration-driven, with an offline stub for tests and local dev.
- Keep the full stack runnable end-to-end with zero external API keys (recommender + broker stubs).

**Non-Goals:**
- No technical indicators, price-history ingestion, backtesting, Interactive Brokers, or multi-agent discovery pipeline.
- No live-money trading path is exercised (paper only), though `ALPACA_PAPER=false` is structurally possible.
- No authentication/multi-tenant concerns (single-user local app, as in the sibling projects).

## Decisions

- **Port asset & recommender code with minimal change.** `quantara`'s `assets/` and `recommendations/` packages already match Cadence's conventions and stack. Copy them (renamed `quantara`→`cadence`), then strip the coupling to the dropped `price_history`/`indicators` modules (remove the `/{ticker}/technical-indicators` route and the price-bar relationship/ingestion helpers; keep the daily snapshot). Rationale: fastest path to proven, convention-correct code; alternative (rewrite from scratch) adds risk for no benefit.

- **Re-implement trading-bot storage as SQLAlchemy ORM + Alembic.** trading-bot uses raw psycopg dataclasses with `CREATE TABLE IF NOT EXISTS`. Re-model `portfolios`, `paper_trading_sessions`, `paper_trades`, `session_runs`, `closed_positions`, and `ai_portfolio_events` as `Mapped[]` ORM models across the `portfolios/`, `paper_trading/`, and `ai_portfolio/` packages, each with an Alembic migration; `migrations/env.py` imports every models module. Rationale: consistency with the asset side and a single schema source of truth. Trade-off: more up-front modeling than a straight port.

- **Brokerage behind a `Broker` Protocol.** `broker/base.py` defines a `@runtime_checkable Broker` Protocol plus `broker/models.py` (`Order`/`Position`/`AccountInfo`/`Quote` + enums), with `broker/alpaca.py` (`AlpacaBroker`, `requests`-based) reading `ALPACA_API_KEY/SECRET_KEY` and choosing the paper vs live base URL from `ALPACA_PAPER`, and `broker/stub.py` (`StubBroker`, deterministic in-memory account/positions/quotes) selected when `ALPACA_STUB` is set. A `get_broker()` dependency factory picks the implementation and is overridden in tests. Rationale: mirrors quantara's `MarketDataProvider`/`RecommenderAgent` seam; makes the whole flow testable offline and keeps paper/live a config switch rather than a code change.

- **AI portfolio agents via the shared `build_agent`.** `ai_portfolio/agent.py` defines the structured Pydantic output models (build result + rebalance result and their nested types, ported from trading-bot's `agent/models.py`) and two sync entrypoints (`build_ai_portfolio`, `rebalance_ai_portfolio`) that wrap `asyncio.run(Runner.run(...))` with timeouts, using `build_agent(..., output_type=..., tools=[web_search])` and `settings.AI_PORTFOLIO_MODEL`. Rationale: reuses Cadence's agent wrapper (which forces structured output) instead of trading-bot's separate `agent_factory`; keeps the sync-service/async-SDK boundary identical to the recommender.

- **Background jobs use quantara's single-worker runner pattern.** Build and rebalance jobs run through a `background.py` module modeled on quantara's `RecommendationJobRunner` (single-worker `ThreadPoolExecutor`, futures map, dead-worker reaping, startup orphan cleanup), rather than trading-bot's module-level executor. Recommendation, AI-build, and AI-rebalance runs each get their own runner. The app-factory lifespan reaps orphaned non-terminal runs/events on startup (recommendation runs + AI-portfolio events). Rationale: one concurrency/observability model across all async work; the lifespan reaper prevents "stuck running" rows after a crash/restart.

- **Executor separated from job orchestration.** `ai_portfolio/executor.py` (`AIPortfolioExecutor.execute_build` / `execute_rebalance`) contains only position sizing and order placement against a `Broker`; the `service.py` job flow handles persistence and phase transitions. Rationale: keeps the money-moving logic pure and unit-testable against `StubBroker`.

- **Cron trigger reuses the X-Cron-Token pattern.** `POST /api/v1/ai-portfolio/rebalance-daily` validates `X-Cron-Token` against `settings.REBALANCE_CRON_TOKEN` (empty token rejects all), then fans out to enrolled active sessions — same guard quantara used for its OHLCV cron. The Docker `cron` sidecar (already scaffolded, `35 9 * * 1-5` America/New_York) calls it. Rationale: scheduling decoupled from the web process; consistent secret handling. Alternative (in-process APScheduler) rejected to match the sibling projects' sidecar approach and survive backend restarts.

- **Rebalance timing aligned to US market open.** Default schedule is `09:35 ET` (just after open) and the executor guards on `broker.is_market_open()`, so market orders fill rather than being rejected by a closed market. This differs from trading-bot's `09:00 CET`; both time and timezone are env knobs (`REBALANCE_SCHEDULE`, `TZ`).

- **Frontend mirrors quantara's client structure.** One axios `apiClient`, per-resource typed clients (`assets`, `recommendations`, `portfolios`, `aiPortfolio`, `paperTrading`, `dashboard`) each exposing a query-key factory + raw fns + TanStack hooks; polling hooks (`refetchInterval` until terminal) for recommendation runs and AI-portfolio build/rebalance events. `types/api.ts` hand-mirrors the Pydantic schemas.

## Risks / Trade-offs

- **[AI output places bad/oversized orders]** → Executor caps each position by the allocated capital and available buying power, skips sub-one-share positions, and wraps each ticker in try/except so one bad order can't fail the whole run; the build event is marked `partial` when some orders fail. Paper-only by default bounds real-world impact.
- **[Market-closed order rejection]** → `is_market_open()` guard + open-aligned schedule; closed runs are recorded as `skipped`, not failed.
- **[Long-running AI calls block a worker / leak "running" rows]** → per-run timeouts, single-worker runners that serialize work, dead-worker reaping on status reads, and startup orphan cleanup in the lifespan.
- **[Ported asset code drags in dropped modules]** → explicitly remove the technical-indicators route and price-bar/ingestion helpers during the port; `migrations/env.py` only imports the models that ship in this change.
- **[Stub vs real divergence]** → the stub implements the same `Broker`/`RecommenderAgent` Protocols and routes candidates through the same validation/execution paths, so behavior differences are limited to data content, not control flow. A manual live-paper smoke test with real Alpaca keys is part of verification.
- **[Corporate TLS interception]** → `truststore` is enabled at import (`cadence/__init__.py`); host-dev script runs backend on the host so outbound HTTPS trusts the OS store, matching quantara.

## Migration Plan

Additive only — no existing data to migrate (greenfield). Deploy by running `alembic upgrade head` (the backend container does this on boot); the new migrations create all tables from the schema-light baseline. Rollback is `alembic downgrade` to the baseline. The cron sidecar becomes effective as soon as the rebalance endpoint exists and `REBALANCE_CRON_TOKEN` is set; leaving the token empty is a safe default that disables all triggers.

## Open Questions

None that block implementation. (Live-paper smoke testing requires the user's Alpaca paper keys, which can be supplied at verification time; the stub path covers everything else.)
