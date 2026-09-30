## Why

The AI paper-trading engine enforces **no allocation limits**: `max_allocation_pct`
exists on the session/portfolio but is hardcoded to `1.0` and never applied, there is
no cap on per-asset-class concentration, no floor on diversification, and no cash
buffer — the agent's raw weights are executed as-is on both build and rebalance. A
single name or a single asset class (e.g. crypto) can therefore dominate a portfolio.
Stop-loss protects against a position falling; it does nothing to prevent
over-concentration in the first place. We want deterministic, per-session risk
guardrails that bound concentration up front, mirroring the existing opt-in,
frozen-at-build pattern of stop-loss and technical indicators.

## What Changes

- Add four **per-session, opt-in, frozen-at-build** portfolio risk guardrails, default
  **OFF** for all sessions including existing ones:
  1. **Max % per asset** — cap any single position's target weight. Repurpose the
     existing unused `max_allocation_pct` column (currently `1.0`) rather than adding a
     new column.
  2. **Max % per asset class** — cap the crypto (or stock) share of the portfolio,
     using the asset-class map already threaded through build/rebalance/executor.
  3. **Min # of positions** — a diversification floor. **Not** deterministically
     enforceable by clamping (we cannot invent holdings the agent did not pick), so it
     is a prompt instruction to the agent + an implied ceiling from the per-asset cap +
     a surfaced/logged violation when the agent returns fewer names — **not** a hard
     clamp.
  4. **Cash buffer / max invested %** — scale the post-clamp weight vector so total
     invested ≤ the max-invested fraction; the remainder stays as cash.
- Enforce guardrails 1, 2, and 4 **deterministically** via a shared clamp + redistribute
  + scale helper (iterative water-filling on the normalized target-weight vector),
  applied at **both** the build seam (`executor.execute_build`) and the rebalance seam
  (`executor.execute_rebalance`). The agent may also be told the caps so it plans well,
  but the deterministic pass is the guarantee — enforcement is **not** prompt-only.
- Freeze the config at build time: a new enable flag plus three new parameter columns
  (max asset-class %, min positions, max invested %) on `paper_trading_sessions`
  (Alembic migration + backfill existing rows to disabled/no-op), threaded through
  `AIPortfolioBuildRequest` → router → `AIBuildParams` → `create_session` → session row,
  read back at rebalance off the frozen session row and at build off the params.
- Surface the guardrails on `PaperTradingSessionRead`, the frontend build form
  (`BuildAIPortfolioCard.tsx`), and a session-detail header fact tile mirroring the
  Stop-loss tile.
- No change to the stop-loss or technical-indicator features.

## Capabilities

### New Capabilities
<!-- None. This extends existing capabilities. -->

### Modified Capabilities
- `ai-paper-trading`: build and rebalance must deterministically enforce the per-session
  frozen guardrails (per-asset cap, per-class cap, max-invested/cash buffer) on the
  target-weight vector, freeze the guardrail config at build, read it back at rebalance,
  and expose it on session reads; the min-positions floor is instructed + surfaced, not
  clamped.
- `daily-rebalancing`: the daily rebalance must honor the session's frozen guardrails
  when computing target allocations.
- `app-shell`: the build form gains guardrail controls and the session-detail page gains
  a guardrail fact tile.

## Impact

- **Migration**: new Alembic revision adding the enable flag + three parameter columns to
  `paper_trading_sessions`, backfilling existing rows to disabled/no-op.
- **Backend**: `ai_portfolio/executor.py` (shared clamp/redistribute/scale helper at both
  build and rebalance seams), `ai_portfolio/service.py` (freeze at build, read-back at
  rebalance, min-positions surfacing), `ai_portfolio/agent.py` (prompt caps + min-positions
  instruction), `paper_trading/models.py` + `paper_trading/service.py` (new columns +
  `create_session` kwargs), `api/schemas.py` (`AIPortfolioBuildRequest` fields +
  `PaperTradingSessionRead` fields + validators), `api/routers/ai_portfolio.py`
  (`AIBuildParams` wiring), `config.py` (new default constants alongside
  `STOP_LOSS_DEFAULT_PCT`).
- **Frontend**: `types/api.ts` (`PaperTradingSession` + `AIPortfolioBuildRequest`),
  `pages/portfolios/BuildAIPortfolioCard.tsx` (form controls), `pages/paper-trading/
  PaperTradingSessionPage.tsx` (guardrail fact tile).
- **Tests**: executor clamp/redistribute/scale unit tests, service build-freeze +
  rebalance read-back + min-positions surfacing tests, API request/read tests, frontend
  build-form + fact-tile tests, `tests/fakes.py` agent knobs if needed.
