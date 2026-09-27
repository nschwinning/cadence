## Why

The technical-indicator trend strategy (entry gate + holdings reversal context) is
currently applied to every AI build and every daily rebalance. Not every portfolio
should be a trend-following portfolio, and portfolios built before the strategy
existed should not silently change behavior. Making the strategy an explicit,
per-portfolio opt-in — chosen when the portfolio is built and frozen for its
lifetime — lets a user run some portfolios on the trend strategy and others without
it, and keeps every existing portfolio behaving exactly as it did before.

## What Changes

- Add a per-session **"use technical indicators" flag**, chosen at build time and
  **frozen with the session** (like asset scope and rebalance-prompt version). It
  defaults to **OFF** (opt-in) when the build request omits it.
- **BREAKING (behavioral):** the trend strategy is no longer unconditional. When the
  flag is OFF, technical indicators are disabled for **both** build and rebalance:
  - **Build**: candidates are no longer hard-filtered or annotated by the trend gate;
    the portfolio may enter any in-scope asset (the pre-trend build behavior).
  - **Rebalance**: candidates the session does not hold are no longer hard-filtered
    by the trend gate, and holdings no longer carry indicator/reversal context to the
    AI (the pre-trend candidate/holdings assembly).
  - No per-run trend-decision context is recorded for OFF sessions (already the
    "no gating" case).
  When the flag is ON, the current trend-strategy behavior applies unchanged (build
  gate + rebalance gate + holdings reversal context + per-run trend-decision context).
- **All existing sessions are treated as OFF**: the new column is non-nullable and
  backfilled to `false`, so already-built portfolios keep their prior behavior with
  no trend gate applied.
- Surface a **toggle on the AI build form** (default off) and persist the choice; add
  an optional field to the build request.
- The **nightly universe-wide indicator computation job is unaffected** — it still
  computes snapshots over all assets regardless of any portfolio's flag.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `ai-paper-trading`: the build entry trend gate becomes conditional on the session's
  opt-in flag; the flag is persisted/frozen with the session; per-run trend-decision
  context is recorded only for opted-in sessions.
- `daily-rebalancing`: the rebalance candidate trend gate and the holdings
  indicator/reversal context become conditional on the session's opt-in flag.
- `app-shell`: the AI build form gains a "use technical indicators" toggle (default
  off).

## Impact

- **Schema/migration**: new non-nullable `use_technical_indicators` column on
  `paper_trading_sessions` (default false, backfill existing rows to false); new
  Alembic migration with `down_revision` = current head.
- **Backend**: `AIPortfolioBuildRequest`/`AIBuildParams` gain the flag; `create_session`
  persists it; `run_build_event` freezes it; `_candidates_from_universe` /
  `_build_holdings` (and the build candidate assembly) apply the trend gate only when
  the session opted in; `PaperTradingSessionRead` exposes the flag.
- **Frontend**: build form toggle + `AIPortfolioBuildRequest`/`PaperTradingSession`
  types gain the field.
- **Compatibility**: existing portfolios/sessions default to OFF (no behavior change);
  the nightly indicator job and stored snapshots are unaffected.
