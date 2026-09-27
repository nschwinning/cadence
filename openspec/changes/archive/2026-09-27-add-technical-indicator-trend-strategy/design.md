# Design: Technical-indicator trend strategy (v3)

## Context

The v2 rebalance prompt trades on fundamentals, news, and P&L only — it has no
view of price trend or momentum. This change adds a `technical-indicators`
capability (compute + nightly job + storage + cron trigger) ported from
quantara's pure-pandas engine, restricted to a close+volume subset, and wires its
output into the two AI trading flows as an **asymmetric two-path decision**:
new entries are hard-gated deterministically; existing holdings are handed to the
LLM with trend/reversal context for an AI-decided exit.

Grounding facts confirmed against the codebase:
- Migration head is `e5c9a3f7d2b8`.
- `HistoryBar` (`assets/market_data.py`) already carries full OHLCV; `close` and
  `volume` are always populated. Restricting to close+volume is a scoping choice.
- `MarketDataProvider.fetch_history(ticker)` returns `list[HistoryBar]`.
- Candidate/holdings assembly lives in `ai_portfolio/service.py`:
  `_candidates_from_universe` (line ~1031), `_build_holdings` (~1094); build uses
  them at ~278, rebalance at ~540–541. `provider` is already threaded into both
  `build_*` and `run_rebalance_event`.
- The cron-token pattern is `require_valid_cron_token` /
  `REBALANCE_CRON_TOKEN` / `X-Cron-Token` (`api/routers/ai_portfolio.py`,
  `config.py`). `hmac.compare_digest`; empty configured token rejects all.
- `pandas`/`numpy` already present — no new dependencies.

## Goals / Non-goals

**Goals**
- A nightly job computes ~14 close+volume indicators + a deterministic uptrend
  gate + reversal flags for every asset, storing the latest snapshot per asset.
- New entries (build + rebalance candidates) are hard-filtered by the gate.
- Holdings always get full indicators + reversal flags for AI-decided exits.
- A v3 rebalance prompt seeded via migration drives the two-path strategy.

**Non-goals (deferred to a later phase)**
- OHLC-only indicators (ATR, ADX, Stochastic).
- Richer swing-based divergence detection (only simple deterministic proxies here).
- Backtesting and risk management (mechanical stop-loss, volatility position sizing).
- No change to the AI output schema.

## Decisions

### 1. New `technical_indicators/` package (port from quantara)
Mirror quantara's layout, restricted to close+volume:
- `compute.py` — pure pandas/numpy engine. Input: an ordered close (prefer
  `adj_close`, fall back to `close`) + volume series built from
  `provider.fetch_history(ticker)`. Output: a dataclass of the fixed indicator
  set, the derived gate verdict, and the reversal flags. No TA-Lib.
- `constants.py` — indicator periods and **tunable gate thresholds** (SMA
  windows, RSI 14 Wilder, ROC 120, Bollinger 20/2σ, divergence lookback N,
  slope window 20, hvol 20). Gate: regime = `close>SMA200 AND SMA50>SMA200 AND
  SMA200_slope>=0`; momentum = `MACD_hist>0 AND RSI14>50 AND ROC120>0`;
  OBV-rising = soft bonus only.
- `models.py` — two SQLAlchemy tables (below).
- `service.py` — compute-and-store one asset (delete-then-insert / upsert the
  single latest row), read latest snapshot(s) by asset id.
- `runner.py` / background — single-worker `ThreadPoolExecutor(max_workers=1)`
  (quantara pattern); one run at a time; commit per asset; per-asset failures
  recorded, run continues.

### 2. Storage: latest snapshot + run audit
- `technical_indicator` — **one row per asset** (unique on asset id): asset FK,
  `trading_date`, every indicator column (nullable — absent when history is
  insufficient), the boolean gate verdict + component sub-verdicts, and the
  boolean reversal flags. Recompute replaces the row (delete-then-insert or
  upsert), so a read always sees the newest snapshot. No history table (matches
  the "latest snapshot per asset" decision; avoids quantara's wide time series).
- `technical_indicator_run` — audit: status, started/finished, processed/failed
  counts.
- **Migration 1** (`down_revision = e5c9a3f7d2b8`) creates both tables.
- **Migration 2** seeds `rebalance_prompt` v3 (append-only; freeze design already
  auto-adopts the highest version for new builds). `down_revision` = migration 1.
  Verify the chain with `alembic heads` before writing (single linear head).

### 3. Wiring into the trading flows (`ai_portfolio/service.py`)
- **Candidates (no position)** — `_candidates_from_universe` (or a new helper it
  delegates to) reads each in-scope asset's latest snapshot, **drops** any asset
  whose gate fails or that has no snapshot, and annotates survivors with their
  trend indicators. Applies identically at build (~278) and rebalance (~540).
  Discovered assets are also gate-checked before being offered as candidates.
- **Holdings (already long)** — `_build_holdings` attaches each holding's full
  indicator set + reversal flags to the payload handed to the AI. **No hard
  exit** — the LLM decides sell/trim/hold.
- Reads use stored snapshots only (no inline compute in the trading path), so a
  rebalance never blocks on indicator computation.

### 4. Prompt v3 (seeded via migration, append-only)
Two-part instructions: (1) allocate among the already-trend-confirmed candidates
by conviction using their indicators; (2) for each holding, judge sell/trim/hold
from its indicators + reversal flags. Retains all v2 constraints (long-only,
weights ≈ 1.0, transaction-cost discipline, crypto 24/7 tickers, discovery /
web-search caps). **No output-schema change** — omit / ~0 weight = exit.

### 5. Cron trigger + schedule
New endpoint under `/api/v1` guarded by the existing cron-token dependency
(`require_valid_cron_token`), starting the job in the background and returning
immediately. New busybox-crond entry in docker-compose to run it nightly
(before the market-open rebalance so snapshots are fresh). Reuse the existing
cron-token config rather than introducing a new secret.

### 6. Per-run trend-decision context (Runs page)
So the Runs page shows the full picture, each build/rebalance run persists the
trend decision that shaped it. Reuse the exact pattern the `research` transcript
already uses (confirmed in the code):
- **Persist** — add a nullable `trend_context` JSONB column to
  `ai_portfolio_events` (`ai_portfolio/models.py`, alongside `research` at
  ~line 90). New Alembic migration modeled on
  `e1f4c2a7b9d5_link_trades_to_ai_runs_and_research.py` (the migration that added
  `research`); `down_revision` = the v3-prompt-seed migration (keep one linear head).
- **Shape** — `{ "dropped_candidates": [{ "ticker", "reason" }], "candidates":
  [{ "ticker", "indicators": {...} }], "holdings": [{ "ticker", "indicators":
  {...}, "reversal_flags": {...} }] }`. `reason` names the failed gate condition
  (or "no snapshot"). Build runs record an empty `holdings` list.
- **Capture** — build the blob at the `_candidates_from_universe` (build ~278,
  rebalance ~540) and `_build_holdings` (~541) seams. Pre-declare
  `trend_context` before the `try` (mirroring `research` at ~271/471) so a mid-run
  failure keeps what was gathered, and set it in `_finish_event` /`_fail_event`
  (`if trend_context: event.trend_context = trend_context`, mirroring `research`
  at ~1259 and ~1275). Runs on a pre-trend frozen prompt version leave it null.
- **Expose** — add `trend_context` to `AIPortfolioEventRead` (`api/schemas.py`
  ~after line 524); it then flows through both the run list and
  `GET /ai-portfolio/runs/{event_id}` automatically (both wrap that schema).
- **Render** — add `trend_context` to the frontend `AIPortfolioEvent` type
  (`types/api.ts` ~after 543) with a blob interface (modeled on `AIResearchEntry`),
  and add a trend-decision `Card` to `pages/runs/RunDetailPage.tsx` (modeled on
  `ResearchCard`, ~246-278) inserted into the detail composition; omit the section
  when `trend_context` is null.

## Reversal flags (deterministic, close+volume only)
Booleans derived from the computed series (no raw series shipped to the AI, no
brittle swing detection):
- `macd_hist_rollover` — histogram turned down vs the prior period.
- `rsi_rollover` — RSI peaked and turned down from a high band.
- `return_decel` — return acceleration non-positive (momentum fading).
- `obv_price_divergence` — price makes a new N-day high while OBV (or RSI) does
  not (simple deterministic proxy over a fixed lookback).
- `sma200_slope_flattening` — SMA200 slope near zero / declining.

## Risks / trade-offs
- **Latest-snapshot-only storage** means no indicator history for later
  backtesting; acceptable — backtesting is out of scope and the trading path only
  needs the newest values.
- **Stale snapshots**: if the nightly job fails, the gate reads yesterday's
  values. Acceptable for a daily strategy; the run audit surfaces failures. A
  missing snapshot fails the gate closed (asset dropped), which is the safe side.
- **Gate hard-drops candidates the AI never sees** — intended: the AI cannot
  enter a downtrend. Holdings deliberately keep the AI in the loop for exits.
- **Thresholds as constants** keeps them tunable without a schema/prompt change.

## Migration plan
1. Migration 1: create `technical_indicator` (unique per asset) + `technical_indicator_run`.
2. Migration 2: seed `rebalance_prompt` v3.
3. Deploy computes snapshots on the first nightly cron; until then the gate drops
   assets with no snapshot (safe). Existing sessions keep their frozen prompt
   version; only sessions built after v3 becomes active use the new strategy.

## Open items (tunable, not blocking)
- Exact numeric thresholds/lookbacks (start from quantara's defaults, expose as
  constants).
- Whether OBV-rising bonus feeds candidate ranking hints in the prompt (soft,
  can be added to the annotation without a schema change).
