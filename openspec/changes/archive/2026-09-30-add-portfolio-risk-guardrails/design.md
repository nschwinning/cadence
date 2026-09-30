## Context

See proposal.md — Why. The AI engine currently executes the agent's raw target
weights with no allocation caps. `paper_trading_sessions.max_allocation_pct` and
`ai_portfolios.max_allocation_pct` already exist but are hardcoded to `1.0` and never
read. Two existing opt-in-frozen-at-build features (`use_technical_indicators`,
`stop_loss_enabled`/`stop_loss_pct`) establish the exact plumbing pattern this change
mirrors. Target weights are 0–1 fractions produced by the agent
(`AIPortfolioStock.allocation_pct` on build, `AITargetAllocation.allocation_pct` on
rebalance), summing to ~1.0. Enforcement seams are the two executor entrypoints, which
already normalize weights before sizing (`execute_build`, `execute_rebalance`) and
already receive an `asset_classes` map keyed by canonical ticker.

## Goals / Non-Goals

**Goals:**
- One shared, deterministic enforcement function applied identically at the build and
  rebalance seams, so build-time and rebalance-time portfolios obey the same caps.
- Reuse the existing unused `max_allocation_pct` column for the per-asset cap; add the
  three genuinely new parameters (per-class cap, min positions, max invested) plus a
  single enable flag, following the stop-loss column pattern.
- Default OFF everywhere, including all existing sessions, via migration backfill — no
  behavioural change for any current session.

**Non-Goals:**
- Not changing the agent's model, prompt strategy, or how weights are produced beyond
  telling it the caps (advisory) and the min-position instruction.
- Not enforcing min positions by fabricating holdings — it is instruction + implied
  floor + surfaced observation only.
- Not a new capability, no new domain package, no change to stop-loss or trend features.
- Not retro-applying guardrails to already-built portfolios' existing positions — the
  guardrails act on the *next* build/rebalance's target vector, not as a one-off
  reshuffle of a running session.

## Decisions

### D1: One `enforce_guardrails(weights, asset_classes, caps) -> weights` helper, two call sites
A single pure function operating on a normalized `{ticker: weight}` mapping, called at
`execute_build` (right after the existing normalize step) and `execute_rebalance` (right
after its weight-normalization step). Returns a new weight mapping whose entries sum to
≤ 1.0 (the gap is the enforced cash buffer). Sizing downstream is unchanged — it already
multiplies weight × base capital, so a sub-1.0 sum naturally leaves cash uninvested.
Alternative considered: enforce inside each of `_rebalance_equity`/`_rebalance_crypto` —
rejected because per-class and cross-asset redistribution need the whole vector at once.

### D2: Clamp + redistribute + scale as an iterative water-filling fixed point
The helper runs to a stable point:
1. **Per-asset clamp/redistribute**: any weight above `max_per_asset` is set to the cap;
   the removed excess is redistributed proportionally across tickers still strictly below
   the cap. Repeat until no weight exceeds the cap or no headroom remains.
2. **Per-class clamp/redistribute**: for any asset class whose summed weight exceeds
   `max_per_class`, scale that class's members down to the cap and redistribute the excess
   proportionally to tickers in classes still below their class cap (respecting the
   per-asset cap). Repeat.
3. Iterate 1↔2 to a fixed point (per-class scaling can push an individual name back over
   the per-asset cap, and vice versa). Bounded iteration count with a convergence epsilon;
   on non-convergence, accept the current vector (still cap-respecting by construction of
   the last clamp) — never loop unbounded.
4. **Max-invested scale**: multiply the whole vector by `min(1, max_invested / sum)` so
   the invested fraction ≤ `max_invested`; the remainder is cash.

**Feasibility fallback**: if the caps make full investment impossible (e.g.
`max_per_asset × count < max_invested`, or every class saturated), the vector cannot
absorb all capital — the deficit simply remains as cash rather than forcing weight past a
cap. Caps are hard; full investment is best-effort. This keeps the function total (always
returns a valid capped vector) and matches the spec's "shortfall remains as cash".

### D3: Min positions is not a clamp
Enforcing a *minimum* count deterministically would require inventing holdings the agent
didn't choose — out of scope and undesirable. Instead: (a) the agent is instructed to
return ≥ N names; (b) the per-asset cap already implies a floor of `ceil(1/max_invested_or_1
/ max_per_asset)` names to be fully invested, which the UI can surface; (c) if the agent
still returns fewer than N, the run records a guardrail observation (in the existing
`run_stats` JSONB on `ai_portfolio_events`, alongside the current gate/order counts) — no
failure, no fabrication. This is the honest deterministic reading of "min positions".

### D4: Column strategy — repurpose one, add four
- **Per-asset cap** → reuse existing `max_allocation_pct` (both `paper_trading_sessions`
  and `ai_portfolios`); stop writing the hardcoded `1.0` and instead write the frozen
  per-session value (default `1.0` = no cap when guardrails off).
- **New columns on `paper_trading_sessions`** (mirroring `stop_loss_*`):
  `risk_guardrails_enabled BOOLEAN NOT NULL DEFAULT false`,
  `max_asset_class_pct FLOAT` (nullable; the frozen per-class cap),
  `min_positions INTEGER` (nullable; the frozen floor),
  `max_invested_pct FLOAT` (nullable; the frozen cash-buffer bound).
Nullable params + a non-null boolean flag mirror the stop-loss shape
(`stop_loss_enabled` non-null, `stop_loss_pct` nullable). Read-back at rebalance treats
`risk_guardrails_enabled = false` (or a missing flag on a pre-migration row) as "no caps".

### D5: Defaults live in config.py
New constants beside `STOP_LOSS_DEFAULT_PCT`, e.g.
`GUARDRAIL_DEFAULT_MAX_ASSET_PCT`, `GUARDRAIL_DEFAULT_MAX_ASSET_CLASS_PCT`,
`GUARDRAIL_DEFAULT_MIN_POSITIONS`, `GUARDRAIL_DEFAULT_MAX_INVESTED_PCT`. The request
validators fill missing params from these only when the guardrails are enabled (mirroring
`_default_stop_loss_pct`).

### D6: Build-freeze thread (mirror the stop-loss 7-point path)
`AIPortfolioBuildRequest` fields → router builds `AIBuildParams(...)` →
`AIBuildParams.to_payload`/`from_payload` round-trip → `create_session(...)` kwargs →
session row columns. Build reads the caps off `params`; rebalance reads them off the
frozen `session_row`. `PaperTradingSessionRead` exposes all five values; `types/api.ts`
mirrors them; `BuildAIPortfolioCard.tsx` adds the toggle + parameter inputs; the session
page adds a guardrail fact tile next to the stop-loss tile.

## Risks / Trade-offs

- **[Fixed-point non-convergence between per-asset and per-class passes]** → bounded
  iteration + epsilon; on exhaustion accept the last (cap-respecting) vector. Unit-tested
  with adversarial cap combinations.
- **[Infeasible cap combinations silently under-invest]** → intended per D2; surfaced via
  the min-positions/implied-floor observation and the cash the user sees in the ledger.
  The build form should hint the implied floor so users don't set contradictory caps.
- **[Repurposing `max_allocation_pct` changes a column's meaning]** → it was never read,
  so no behavioural regression; migration backfills existing rows to `1.0` (no cap) and
  the flag to false. Double-checked all read sites (currently none enforce it).
- **[Weights re-normalized then scaled — off-by-a-cent sizing]** → sizing already floors
  to whole shares (equities) / precision (crypto) and skips sub-threshold positions, so
  the cash buffer is approximate to within one share; acceptable and consistent with
  existing behaviour.

## Migration Plan

1. Alembic revision (down_revision = current head): add the four new columns to
   `paper_trading_sessions`; backfill existing rows (`risk_guardrails_enabled = false`,
   params NULL, `max_allocation_pct` left as-is/`1.0`). `ai_portfolios.max_allocation_pct`
   is unchanged structurally.
2. Deploy is additive and default-off; no data reprocessing. Rollback = downgrade drops
   the four columns; `max_allocation_pct` reverts to its prior unused role.

## Open Questions

None blocking. (Exact default cap values — e.g. 25% per asset, 60% per class, 5 min
positions, 95% invested — are tuning constants set in `config.py` during apply and do not
affect the specs or task breakdown.)
