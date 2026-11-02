## Why

Cadence can only trade via AI-driven paper portfolios. There is no way to run a
deterministic, rule-based (non-AI) strategy — a technical-indicator bot — against
the same asset universe and compare it, head to head, with the AI portfolios. The
sibling course project has ~47 such indicator bots whose signal logic is valuable
but whose scaffolding (fake exchange, tick loops, console printing) is throwaway.
This change introduces a separate **strategy-bots** subsystem that deploys
rule-based bots one strategy at a time, shares the existing asset universe, and
shows up alongside AI portfolios on the dashboard for comparison — while keeping
creation and tracking otherwise cleanly separated from AI paper-trading.

## What Changes

- **New strategy-bots subsystem** (backend): own `bot_sessions`, `bot_trades`,
  and `bot_value_snapshots` tables with **no foreign keys** to
  `paper_trading_sessions`; its own `/api/v1/bots` router (including a
  cron-guarded `POST /api/v1/bots/tick`), its own executor and service, and its
  own lifecycle / daily value-snapshot / KPI logic (copied from the paper-trading
  patterns, not shared — the duplication is deliberate, to keep the two domains
  decoupled).
- **Three-layer execution model**: (1) a **strategy** is a pure signal generator
  `evaluate(bars, position, params) -> ENTER_LONG | EXIT | HOLD + reason` with no
  I/O or persisted state; (2) a shared **risk/execution engine** does sizing,
  take-profit/stop-loss, a drawdown kill-switch, order submission, fill polling,
  and fees; (3) a **registry** maps `strategy_key -> {impl, params schema,
  required history}`.
- **One strategy in v1 — MA Crossover**: fast SMA crossing above the slow SMA
  enters long; a down-cross exits. Take-profit / stop-loss are optional
  (nullable). Strategies are deployed one at a time; this is the first.
- **Intraday, long-only, equities-only, single all-in position** for v1: on an
  entry signal the engine deploys ~all session capital minus a cash buffer into
  `floor((capital - buffer) / price)` **whole shares**; one position at a time, no
  pyramiding or scaling-in.
- **Cron-endpoint runner** (not a persistent worker), reusing the existing
  cron-token guard: an external sidecar POSTs `/api/v1/bots/tick`. Default cadence
  is a **5-minute tick on 5-minute bars**; both the tick interval and the signal
  bar timeframe are configurable settings so they can be tuned or decoupled later
  without a redesign. The cron **schedule string** lives in docker-compose/env
  (not in Pydantic Settings), matching the other cron variables.
- **Market-hours gating** via the Alpaca clock (Mon–Fri); ticks outside market
  hours are no-ops. **Stateless recompute** each tick: fetch `slow_period +
  buffer` bars, recompute indicators fresh, and persist only position state, the
  trade ledger, and equity snapshots.
- **Fresh market data — explicit `feed=iex`.** The free tier's "15-minute delay"
  applies to the **SIP** (consolidated) feed, not to **IEX**: the default/SIP REST
  path restricts the most recent ~15 minutes (a 403 unless `end` is ≥15 min old),
  which is the source of the "REST is delayed" behavior — but an **explicit
  `feed=iex` request is real-time** on both REST and websocket. v1 therefore simply
  **requests bars with `feed=iex` explicitly** (never the default/SIP feed) so the
  cron REST-pull tick gets real-time data with no extra infrastructure. The feed is
  a configurable setting so a deployment with a paid SIP subscription can select it.
  Because IEX is a single exchange (~2.5% of volume, not the NBBO), the most recent
  bar may be **sparse or missing**; when a fresh most-recent bar is unavailable for a
  session the tick **skips** that session rather than trading a stale signal. (We
  deliberately do **not** build a websocket collector — it would read the same IEX
  source and so would not improve data quality over `feed=iex` REST; the real
  upgrade is the paid real-time SIP plan, out of scope for v1.)
- **Dashboard comparability** (the one deliberate point of convergence): the
  dashboard overview gains active strategy-bot rows alongside AI-session rows,
  each row carrying a `kind` discriminator (`ai` | `bot`). Bot rows are produced
  by a bots-side adapter that emits the **same per-session performance shape**
  (value series, contributions, since-inception benchmark value, range P&L), so
  the combined-equity chart and leaderboard render bots on the same axes with no
  structural coupling. Bots are badged `Bot` and filterable via the existing
  selection controls. The per-portfolio **AI-cost panel stays AI-only** — bots
  have no LLM spend, so excluding them is correct, not a gap.
- **New "Bots" frontend surface**: a distinct nav entry, a dedicated build form
  (not the AI build card), and its own list and detail pages (KPI tiles, value
  chart, trade ledger) reading `/api/v1/bots`.

## Capabilities

### New Capabilities

- `strategy-bots`: Deterministic, rule-based (non-AI) technical-indicator trading
  bots — bot session lifecycle, the strategy registry and the MA Crossover
  strategy, the shared risk/execution engine (sizing, TP/SL, drawdown
  kill-switch, orders, fills, fees), the cron-guarded tick runner with
  market-hours gating and stateless recompute, daily value snapshots and KPIs,
  and the dashboard performance adapter that exposes bot sessions in the shared
  comparison shape. Shares the asset universe read-only; owns its own persistence.

### Modified Capabilities

- `dashboard`: The range-scoped overview SHALL additionally aggregate active
  strategy-bot sessions, and each per-session performance row SHALL carry a
  `kind` discriminator (`ai` | `bot`) so AI portfolios and bots are comparable in
  one list. The AI-cost breakdown remains AI-only.
- `app-shell`: A new "Bots" navigation entry, bot build/list/detail views, and
  the dashboard combined-equity chart and leaderboard SHALL render bot rows
  alongside AI sessions, visually badged by `kind` and filterable with the
  existing selection controls.

## Impact

- **Backend — new**: `backend/src/cadence/strategy_bots/` package (models,
  service, executor, strategy registry + MA Crossover, errors, constants);
  `backend/src/cadence/api/routers/bots.py`; new Pydantic schemas in
  `api/schemas.py`; new Alembic migration for `bot_sessions`, `bot_trades`,
  `bot_value_snapshots` (+ position state). Reuses `assets.service.list_assets`
  (universe, read-only), the `Broker` protocol + Alpaca impl + fill-polling, the
  benchmark series machinery, and `api/cron_auth.py` (`X-Cron-Token`).
- **Backend — modified**: `dashboard/service.py` (`SessionPerformance` gains
  `kind`; `get_dashboard_overview` unions a bot-side adapter's rows and folds bot
  dates into the benchmark overlay floor) and `api/schemas.py`
  (`DashboardSessionPerformance` gains `kind`). No change to the AI
  paper-trading tables, router, executor, pages, or the `/dashboard/ai-costs`
  endpoint behavior (beyond staying AI-only).
- **Frontend**: new `Bots` nav entry (`Sidebar.tsx`), a `BuildBotCard`, bot list
  and detail pages, a new `/api/v1/bots` typed client + hooks, and `kind` added
  to the dashboard session type with badge/filter rendering in the combined-equity
  chart and leaderboard. Dashboard fixtures gain a bot row.
- **Config**: new Pydantic settings for the bot tick interval and signal bar
  timeframe (with defaults = 5 minutes) and a `BOT_MARKET_DATA_FEED` setting
  (default `iex`) so the real-time IEX feed is requested explicitly and a paid SIP
  subscription can be selected instead; a new cron schedule string in
  docker-compose/env (e.g. `*/5 13-20 * * 1-5`).
- **New dependencies**: none. MA Crossover needs only arithmetic over recent bars
  (no statsmodels), and `feed=iex` bars come through the existing Alpaca market-data
  REST path — no websocket collector, no new process, no new third-party dependency.

## Assumptions (for review)

1. **Active-only on the dashboard.** The overview includes **active** bot
   sessions only, matching the existing `SessionStatus.ACTIVE` filter for AI
   sessions; stopped/archived bots are excluded from the overview just as
   stopped/archived AI sessions are. (Narrowable at review.)
2. **Position state storage.** v1's single-position model makes storing position
   state as columns on `bot_sessions` viable rather than a separate
   `bot_positions` table; the final choice is made in design.
3. **Bot row label.** Each bot gets a distinct display label derived from its
   strategy + traded asset (e.g. "MA Crossover · AAPL"), used as the dashboard
   row label and badge text source.
4. **Benchmark.** A bot picks a single benchmark (default S&P 500) for
   comparability, reusing the existing benchmark-series / rebased-value
   machinery so the since-inception benchmark overlay works identically to AI
   sessions.
5. **Market-data freshness via explicit `feed=iex`.** The intraday tick must act on
   data current to the signal bar timeframe. The free tier's 15-minute restriction
   applies to the **SIP** (consolidated) feed, not **IEX**: an explicit `feed=iex`
   REST request is real-time, so the cron REST-pull tick is sufficient with no
   streaming infrastructure — we just request `feed=iex` explicitly rather than the
   default/SIP feed. **Trade-off recorded:** real-time IEX is a single exchange
   (~2.5% of volume, not the NBBO) and may have sparse/missing recent bars; Alpaca
   cautions IEX is incomplete for live-trading decisions. v1 accepts this for a
   free-tier paper bot on liquid names and **skips** a session when a fresh recent
   bar is unavailable. We deliberately do **not** build a websocket collector (same
   IEX source → no quality gain over `feed=iex` REST) and do **not** buy a real-time
   SIP subscription; the paid SIP plan is the genuine upgrade if data quality later
   matters. (Narrowable at review — e.g. restricting v1 to daily/EOD bars, where the
   delay/sparseness is immaterial.)
