## Context

Cadence trades only through AI-driven paper portfolios. We want a parallel,
deterministic, rule-based bot subsystem that (a) shares the asset universe,
(b) is comparable with AI portfolios on the dashboard, and (c) is otherwise
cleanly separated in creation and tracking. The design question is where the two
domains touch and where they stay apart. The guiding principle:

> **Separate everything on the write/domain side; converge at exactly two
> deliberate read seams — the universe (input) and the dashboard comparison
> contract (output).** Neither subsystem imports the other; the dashboard is the
> single aggregator that depends on both, which is correct because it is the
> consumer layer, not a domain.

The subsystem follows the established Cadence package convention
(`models.py` + `service.py` + `errors.py` + `constants.py`, thin router, external
I/O behind Protocols, Alembic-owned schema).

## Goals / Non-Goals

**Goals (v1)**
- A `strategy_bots` backend package with its own persistence and `/api/v1/bots`
  router, including a cron-guarded `/tick`.
- A three-layer execution model (pure strategy / shared risk-execution engine /
  registry) so later strategies are additive.
- One strategy: MA Crossover. Intraday, long-only, equities-only, single all-in
  whole-share position, optional TP/SL, drawdown kill-switch.
- Stateless-recompute tick runner, market-hours gated, cadence + bar timeframe
  configurable (default 5 min / 5 min).
- Dashboard comparability via a `kind` discriminator + a bots-side performance
  adapter emitting the existing per-session shape.
- A "Bots" frontend area (nav + build + list + detail).

**Non-Goals (v1)**
- Backtesting / historical preview; crypto; shorting; fractional or scaling-in
  sizing; multi-position; a second strategy.
- Any change to AI paper-trading tables/router/executor/pages, or to the
  `/dashboard/ai-costs` endpoint behavior (beyond staying AI-only).
- Sharing lifecycle/snapshot/KPI code with paper-trading (deliberately copied).

## Decisions

### Separate persistence, no cross-domain FKs
New tables, no foreign keys to `paper_trading_sessions`:

- `bot_sessions` — id, strategy_key, asset_id (FK → `assets`), label, status
  (active|stopped|archived), benchmark id, initial/allocated capital, strategy
  params (JSONB), optional take_profit_pct / stop_loss_pct, drawdown_stop_pct,
  cash buffer, peak_value (for drawdown), timestamps, and **position state**
  (see below).
- `bot_trades` — id, bot_session_id (FK → `bot_sessions`), side (buy|sell),
  ticker, quantity, filled_price, fees, broker order id, status, created_at.
- `bot_value_snapshots` — id, bot_session_id, snapshot_date, total_value,
  realised_pnl, unrealised_pnl; unique `(bot_session_id, snapshot_date)`.

**Position state on `bot_sessions` columns, not a `bot_positions` table.** v1 holds
at most one position per session, so columns (`position_qty`, `position_avg_price`,
`position_opened_at`, nullable when flat) are simpler and sufficient. A separate
table would only pay off with multi-position support, which is a non-goal.
*(Assumption #2 resolved toward columns; revisit if multi-position lands.)*

### Three-layer execution model
- **Strategy (pure):** `evaluate(bars, position, params) -> Signal` where
  `Signal ∈ {ENTER_LONG, EXIT, HOLD}` + reason. No I/O, no persisted state →
  trivially unit-testable. MA Crossover computes two SMAs over the supplied bars
  and compares the latest two cross states.
- **Risk/execution engine (shared):** given a signal + live price + session state,
  it does sizing (`floor((capital - buffer)/price)` whole shares), submits orders
  via the `Broker` protocol, polls fills to terminal, applies TP/SL and the
  drawdown kill-switch, records trades, and updates position state. Reused by every
  strategy.
- **Registry:** `strategy_key -> {impl, params_schema, required_history}`. The
  runner uses `required_history` to size the bar fetch and `params_schema` to
  validate creation params. MA Crossover is the only registered entry in v1.

### Cron-endpoint runner, stateless recompute, market-hours gated
`POST /api/v1/bots/tick`, guarded by `require_valid_cron_token`
(`api/cron_auth.py`, `X-Cron-Token`). The sidecar's cron schedule string lives in
docker-compose/env (e.g. `*/5 13-20 * * 1-5`), **not** Pydantic Settings — matching
`REBALANCE_SCHEDULE`/`SNAPSHOT_SCHEDULE`. The **tick interval** and **signal bar
timeframe** *are* Pydantic settings (new, defaults = 5 min) so they are tunable and
decoupleable (check exits every tick; compute entries on a slower bar) without a
redesign.

Each tick: if the broker clock reports the market closed → no-op. Otherwise, per
active session: fetch `required_history + buffer` bars at the configured timeframe
**from the configured market-data source** (see next decision), recompute indicators
fresh, evaluate, then run the engine (TP/SL and drawdown checked regardless of the
strategy signal). Nothing is cached across ticks in the *runner*; the DB holds
position state + ledger + snapshots. This keeps the runner crash-safe and
restartable, and mirrors how the course bots behave without their in-memory
`deque`.

### Market-data freshness: explicit `feed=iex`
A 5-minute tick is only meaningful if the bars are current to ~5 minutes. The free
tier's reputed "REST is 15-minutes delayed" behavior is specific to the **SIP**
(consolidated) feed: on the free plan the most recent ~15 minutes of SIP data are
restricted (a `feed=sip` request with a near-now `end` 403s), and because the REST
default is "the best feed your subscription allows," an unspecified feed trips that
restriction. **An explicit `feed=iex` request is real-time on the free tier** — on
both REST and websocket — with no 15-minute rule (Alpaca's own guidance for recent
free-tier data is "use `feed=iex` or the paid plan").

Decision: the tick fetches bars via **REST with `feed=iex` set explicitly** (never
the default/SIP feed). This fixes the latency concern with a one-parameter choice and
keeps the simple, Pi-friendly, stateless cron-pull architecture — no streaming
process. The feed is a configurable setting (`BOT_MARKET_DATA_FEED`, default `iex`)
so a deployment with a paid real-time SIP subscription can select `sip`. The tick
reads through a small `MarketData` seam (a `feed=iex` REST implementation in v1) so
the source is swappable without touching strategy or engine code.

**Why not a websocket collector:** a streaming subscriber would read the **same IEX
source** and so would not improve data quality over `feed=iex` REST — it would only
avoid occasional trailing-bar gaps, at the cost of an always-on process + reconnect
handling on the Pi. That trade is not worth it. A **full event-driven runner** is
likewise out of scope for v1.

**Known limitation (accepted, documented):** real-time IEX is a single exchange
(~2.5% of US volume, not the NBBO), so the most recent bar can be **sparse or
missing** and Alpaca cautions IEX is incomplete for live-trading decisions. For a
free-tier paper bot on liquid large-caps at ≥5-minute bars this is acceptable. When a
fresh most-recent bar is unavailable for a session, the tick **skips** that session
(leaving position + ledger untouched) rather than acting on a stale signal. The
genuine quality upgrade — if it ever matters — is the paid real-time **SIP** plan,
which the `BOT_MARKET_DATA_FEED` setting already allows selecting; it is not bought in
v1.

### Seam 1 — shared universe (input, read-only)
The engine reads the universe via `assets_service.list_assets(session,
membership=...)`, the same function the AI executor uses
(`ai_portfolio/flows/rebalance.py`). The minimal Asset contract it needs:
`{ticker, alpaca_symbol, fractionable, category, is_eligible}`. A bot session
references one asset by `asset_id`/ticker and reads its row live each tick. One
universe, two independent readers — no duplication, no sync. Creation rejects a
non-eligible or non-equity asset.

### Seam 2 — dashboard comparison (output, read-only adapter)
The dashboard router does `DashboardOverview.model_validate(get_dashboard_overview
(...))` — a pure attribute copy. So any object with the same attribute names as
`SessionPerformance` renders in the combined-equity chart and leaderboard unchanged.

1. Add `kind: Literal['ai','bot']` (default `'ai'`) to the `SessionPerformance`
   dataclass (`dashboard/service.py`) and to `DashboardSessionPerformance`
   (`api/schemas.py`). Existing AI rows default to `'ai'`.
2. `get_dashboard_overview` gathers a second batch:
   `bot_rows = strategy_bots_service.dashboard_performance(session, range_,
   broker, ...)` — the **adapter**, living in the bots subsystem, returning
   `SessionPerformance`-shaped objects with `kind='bot'` built from
   `bot_value_snapshots` + bot KPIs, reusing `load_benchmark_series` /
   `rebased_benchmark_value` so the since-inception benchmark value matches AI
   sessions. `rows = ai_rows + bot_rows`.
3. The benchmark overlay floor (`overlay_floor` / `_benchmark_overlays`) folds in
   bot point dates + contributions so the shared benchmark axis starts at the
   earliest of either domain.

The chart + leaderboard iterate `sessions` generically, so they need no logic
changes — bots appear as more rows. The frontend `kind` field drives a **badge**
and keeps bots filterable via the existing selection checkboxes; a bot leaderboard
row links to the bot detail route rather than the paper-trading route.

**AI-cost panel stays AI-only.** Bots have no LLM spend; a bot's only cost is
trading fees, already carried in the row's `fees`. `/dashboard/ai-costs` continues
to list only AI sessions — correct, not a gap.

### Frontend separation
New `Bots` nav entry in `Sidebar.tsx`; a `BuildBotCard` (strategy + asset +
capital + benchmark + params + optional TP/SL); bot list + detail pages with their
own KPI tiles, value chart, and trade ledger; a new `/api/v1/bots` typed client +
hooks mirroring the paper-trading client. The only shared screen is the dashboard,
deliberately, with per-row kind badges.

## Risks / Trade-offs

- **Copied lifecycle/snapshot/KPI logic** (vs shared): accepted — keeps the two
  domains decoupled and lets the bot domain evolve (intraday cadence, different
  KPIs) without destabilizing AI paper-trading. Revisit if drift becomes costly.
- **Stateless recompute cost per tick**: negligible — a handful of SMAs over a
  small bar window; `feed=iex` REST volume keeps us well under Alpaca rate limits
  even at 5-minute cadence across many sessions.
- **Market-data latency**: the free-tier 15-minute restriction is SIP-only;
  mitigated by requesting `feed=iex` explicitly (real-time on the free tier), so the
  cron REST-pull tick is current to the cadence with no streaming process.
- **IEX incompleteness (accepted)**: real-time IEX is one exchange (~2.5% of volume,
  not the NBBO); recent bars can be sparse/missing and IEX is not ideal for
  live-trading decisions. Accepted for a free-tier paper bot on liquid names; the
  tick skips a session when a fresh recent bar is unavailable rather than trading
  stale. A paid SIP subscription (selectable via `BOT_MARKET_DATA_FEED`) is the real
  upgrade, not bought in v1.
- **Intraday fills on paper**: market/slippage behavior differs from the AI daily
  path; fees/buffer handling is isolated in the engine so it can be tuned.
- **Dashboard coupling to a bots adapter**: the dashboard now imports the bots
  service. This is the intended single convergence point; the dependency is
  one-directional (dashboard → bots), and the contract is the attribute shape, not
  bot tables.

## Migration Plan

Single additive Alembic migration creating `bot_sessions`, `bot_trades`,
`bot_value_snapshots` (down_revision = current head). No changes to existing
tables; the dashboard changes are read-model/schema-field additions only
(`kind` defaults to `'ai'`, backward compatible). No data backfill. Rollback drops
the three new tables.

## Open Questions

- Default cash buffer and drawdown limit values for bots (reuse existing
  rebalance-buffer defaults, or bot-specific settings?). Proposed: bot-specific
  settings with sensible defaults, finalized during apply.
- Whether bot value snapshots should run on the existing snapshot cron or a
  bot-specific one. Proposed: reuse the daily snapshot cadence via a bot-specific
  cron-guarded endpoint, consistent with the AI snapshot pattern.
