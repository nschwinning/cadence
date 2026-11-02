## 1. Persistence and configuration

- [x] 1.1 Create the `strategy_bots` package (`models.py`, `service.py`, `errors.py`, `constants.py`) with the `BotSession`, `BotTrade`, `BotValueSnapshot` ORM models and position-state columns on `BotSession`; verify `uv run mypy src/cadence` passes on the new models
- [x] 1.2 Add an Alembic migration creating `bot_sessions`, `bot_trades`, `bot_value_snapshots` (no FK to `paper_trading_sessions`; unique `(bot_session_id, snapshot_date)`); verify the migration round-trips (upgrade then downgrade) against the test DB
- [x] 1.3 Add Pydantic settings for the bot tick interval and signal bar timeframe (defaults = 5 minutes) plus bot cash-buffer and drawdown-limit defaults, and a `BOT_MARKET_DATA_FEED`/data-source-mode setting selecting `rest` (verified real-time) vs `stream` (collector-backed), default `rest`; verify a unit test reads the defaults from `settings`
- [x] 1.4 Add the bot cron schedule string (e.g. `*/5 13-20 * * 1-5`) and the bot snapshot schedule to docker-compose/env only (not Pydantic Settings); verify the compose config references the new cron entries

## 2. Strategy layer and registry

- [x] 2.1 Define the pure strategy contract `evaluate(bars, position, params) -> Signal(ENTER_LONG|EXIT|HOLD, reason)` and the `Signal` type; verify a typed stub strategy compiles under mypy
- [x] 2.2 Implement the MA Crossover strategy (fast SMA up-cross → ENTER_LONG, down-cross → EXIT, else HOLD, insufficient history → HOLD); verify unit tests cover up-cross, down-cross, hold, and insufficient-history cases
- [x] 2.3 Implement the registry mapping `strategy_key -> {impl, params_schema, required_history}` with MA Crossover registered; verify a unit test resolves MA Crossover's required history and validates its params schema

## 3. Risk / execution engine

- [x] 3.1 Implement all-in whole-share sizing `floor((capital - buffer)/price)` and long-only buy submission with fill polling via the `Broker` protocol; verify a unit test with `StubBroker` asserts the share count and recorded fill, and that no pyramiding occurs when a position is already open
- [x] 3.2 Implement EXIT (sell entire position, poll to terminal) and the long-only guard (never open a short); verify unit tests for full-exit and the short-guard
- [x] 3.3 Implement optional take-profit and stop-loss exits (nullable thresholds, evaluated independently of the strategy signal); verify unit tests for TP trigger, SL trigger, and both-unset-never-trigger
- [x] 3.4 Implement the drawdown kill-switch (exit any position and stop the session when value falls by the drawdown limit from peak); verify a unit test drives value below the limit and asserts the session is stopped and flat

## 4. Market-data source (real-time `feed=iex`)

- [x] 4.1 Define a `MarketData` seam (`latest_bars(symbol, timeframe, count) -> bars` carrying an as-of/freshness guarantee) behind which the tick reads bars; verify a typed stub compiles under mypy
- [x] 4.2 Implement the REST `MarketData` that requests bars with **`feed=iex` set explicitly** (never the default/SIP feed), wired to the `BOT_MARKET_DATA_FEED` setting (default `iex`, `sip` selectable for a paid subscription); verify a unit test asserts `feed=iex` is sent, bars are returned via a stubbed REST client, and a stale/old most-recent bar is reported as "fresh unavailable"
- [x] 4.3 Document in the change the accepted IEX-incompleteness trade-off (single exchange, sparse recent bars, not for critical live-trading decisions) and that paid SIP via `BOT_MARKET_DATA_FEED=sip` is the upgrade path; no code beyond the setting

## 5. Session service and tick runner

- [x] 5.1 Implement `strategy_bots.service` session CRUD + lifecycle (create bound to a universe asset via `assets_service.list_assets`, reject unknown strategy / non-eligible non-equity asset, stop, archive); verify unit tests for create, rejection, and stop→archive transitions
- [x] 5.2 Implement the stateless-recompute tick (fetch `required_history` bars **via the configured `MarketData` source**, recompute, evaluate, run the engine) with market-hours gating via the broker clock; **skip a session when fresh bars within the freshness bound are unavailable** (leave its position/ledger unchanged); verify unit tests: market-closed no-op, only-active-sessions ticked, a full recompute path with `StubBroker` + stubbed clock + stub `MarketData`, and a stale/missing-data skip
- [x] 5.3 Implement daily bot value snapshots and per-session KPIs computed from the bot's own ledger + snapshots; verify unit tests for snapshot recording and KPI computation

## 6. API router and schemas

- [x] 6.1 Add `api/routers/bots.py` mounting under `/api/v1/bots` with create/list/detail/stop/archive endpoints and the bot KPI/value-history/trade-ledger reads; verify router tests exercise the happy paths and domain-error → HTTP mappings
- [x] 6.2 Add the cron-guarded `POST /api/v1/bots/tick` (and the bot snapshot endpoint) using `require_valid_cron_token`; verify tests for the 200 authorized path and the rejected unauthenticated path
- [x] 6.3 Add the bot Pydantic request/response schemas in `api/schemas.py`; verify `model_validate` maps the service dataclasses and mypy passes

## 7. Dashboard comparison seam

- [x] 7.1 Add `kind: Literal['ai','bot']` (default `'ai'`) to the `SessionPerformance` dataclass and `DashboardSessionPerformance` schema; verify existing dashboard tests still pass with AI rows defaulting to `'ai'`
- [x] 7.2 Implement `strategy_bots.service.dashboard_performance(...)` adapter returning `SessionPerformance`-shaped rows with `kind='bot'`, reusing `load_benchmark_series`/`rebased_benchmark_value`; verify a unit test asserts the shape incl. `kind`, value series, contributions, and benchmark value
- [x] 7.3 Union bot rows into `get_dashboard_overview` and fold bot dates/contributions into the benchmark overlay floor; verify a unit test asserts AI+bot rows are both returned and the overlay floor includes the earliest bot date

## 8. Frontend

- [x] 8.1 Add the `/api/v1/bots` typed client + TanStack Query hooks and `types/api.ts` mirrors (incl. `kind` on the dashboard session type); verify `npm run typecheck` passes
- [x] 8.2 Add the "Bots" nav entry (`Sidebar.tsx`), the `BuildBotCard`, and the bot list + detail pages (KPI tiles, value chart, trade ledger); verify vitest renders the build form, list, and detail
- [x] 8.3 Render `kind` badges in the combined-equity selection list and the leaderboard, and route bot leaderboard rows to the bot detail; update dashboard fixtures to include a bot row; verify vitest for badging, filtering a bot row, and the bot-detail link

## 9. Verification

- [x] 9.1 Run backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` — all green
- [x] 9.2 Run frontend gates: `cd frontend && npm run typecheck && npm run test && npm run build` — all green
- [x] 9.3 Run `openspec validate add-strategy-bots-subsystem --strict` — valid
