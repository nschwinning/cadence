## Why

The AI rebalance prompt (currently v2) trades on fundamentals, news, and P&L
alone — it has no view of price trend or momentum, so it can buy assets in
confirmed downtrends and has no systematic signal for when a holding's trend is
breaking down. Introducing technical indicators lets Cadence "trade trend":
only enter assets in a confirmed uptrend, and give the AI trend/reversal
context when deciding whether to hold or sell existing positions.

## What Changes

- **New `technical-indicators` capability**: a nightly job computes a fixed set
  of close+volume technical indicators (SMA/EMA structure and slope, MACD, RSI,
  ROC/momentum, OBV, volume ratio, distance-from-52w-high, drawdown, historical
  volatility, Bollinger %b/bandwidth) for every asset in the universe, plus a
  small set of deterministic **reversal flags** derived from them. Results are
  stored as the **latest snapshot per asset** (one upserted row per asset), with
  a run-audit record, a single-worker background runner, and a cron-triggered
  HTTP endpoint guarded by the shared cron token.
- **New deterministic trend gate**: from an asset's latest indicators the system
  derives a hard pass/fail "uptrend" verdict (regime + momentum conditions) and,
  for held assets, a set of reversal flags — both exposed to the trading flows.
- **`daily-rebalancing` v3 strategy (asymmetric two-path decision)**:
  - *Candidates the session does not hold* are **hard-filtered** by the trend
    gate — assets that fail are dropped and never shown to the AI.
  - *Current holdings* are **never hard-exited**; their full indicator set and
    reversal flags are attached to the prompt and the **AI decides** sell / trim
    / hold. (No mechanical stop-loss in this change — see Out of scope.)
  - A new append-only **rebalance prompt v3** (seeded via migration; the existing
    freeze design auto-adopts the highest version for new builds while existing
    sessions keep their frozen version) with two-part instructions: allocate
    among the already-trend-confirmed candidates by conviction, and judge each
    holding's sell/hold from its technicals + reversal flags. Existing
    constraints are retained (long-only, weights sum ≈ 1.0, transaction-cost
    discipline, crypto handling, discovery/web-search caps). **No change to the
    AI output schema** — omitting a holding (or ~0 weight) still means sell.
- **`ai-paper-trading` build-time consistency**: the same trend gate hard-filters
  candidates at initial build (a fresh session has no holdings, so every
  candidate is gated), so a portfolio is never *initialised* with assets the
  rebalance path would refuse to enter.
- **Per-run trend-decision context on the Runs page**: each build/rebalance run
  persists the trend picture that shaped it — the candidates the gate dropped
  (with the reason each failed) and the indicator annotations handed to the AI for
  the surviving candidates and the holdings (with reversal flags) — recorded on the
  AI-portfolio event next to the reasoning/research transcript (best-effort, so a
  mid-run failure still keeps what was gathered), returned in the run detail, and
  rendered as a new section on the run detail view so the full picture is visible.

## Capabilities

### New Capabilities
- `technical-indicators`: Compute a fixed set of close+volume technical
  indicators and deterministic trend-gate / reversal signals per asset on a
  nightly schedule, store the latest snapshot per asset with a run audit, and
  expose them for consumption by the trading flows.

### Modified Capabilities
- `daily-rebalancing`: Rebalance candidate assembly is hard-filtered by the
  trend gate; current holdings carry technical/reversal context into the prompt
  for AI-decided exits; a new rebalance prompt version (v3) drives the strategy.
- `ai-paper-trading`: Build-time candidate assembly is hard-filtered by the same
  trend gate so initial portfolios only enter trend-confirmed assets; each run
  persists and exposes its trend-decision context (dropped candidates + indicator
  annotations for survivors and holdings) in the run detail.
- `app-shell`: The run detail view gains a trend-decision section showing what the
  gate filtered out and what indicators were handed to the AI.

## Impact

- **New DB tables** (Alembic migration, `down_revision = e5c9a3f7d2b8`): a
  latest-snapshot indicator table (one row per asset) and an indicator-run audit
  table. Plus a second migration seeding `rebalance_prompt` version 3, and a third
  migration adding a nullable `trend_context` JSONB column to `ai_portfolio_events`
  (modeled on the existing `research` column).
- **New backend package** `technical_indicators/` (compute ported from
  quantara's pure-pandas engine, restricted to the close+volume subset; models,
  service, background runner, constants). New router + cron endpoint under
  `/api/v1`; new cron-sidecar schedule in docker-compose.
- **Modified** `ai_portfolio/service.py` candidate/holdings assembly (both build
  and rebalance) to read stored indicators, apply the gate, and attach context;
  new v3 prompt row. The build/rebalance flows also capture the trend-decision
  context and persist it via the existing `_finish_event`/`_fail_event` seams
  (mirroring the `research` best-effort pattern).
- **Read model + frontend**: `AIPortfolioEventRead` gains `trend_context` (flows
  through the run list + detail endpoints); the frontend `AIPortfolioEvent` type
  gains a matching field with a blob interface, and the run detail page
  (`pages/runs/RunDetailPage.tsx`) gains a trend-decision card (modeled on the
  existing research card).
- **Dependencies**: `pandas` / `numpy` already present — no new dependencies.
- **Config**: a new cron token / schedule env for the indicator job (reuse the
  existing cron-token pattern) and tunable gate thresholds as constants/settings.
- **Data note**: `HistoryBar` already carries full OHLCV, so restricting v3 to
  close+volume is a scoping choice, not a data limit.
- **Out of scope (deferred to a later phase)**: OHLC-only indicators (ATR, ADX,
  Stochastic), richer swing-based divergence detection, backtesting, and risk
  management (mechanical stop-loss / volatility-based position sizing).
