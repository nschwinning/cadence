## Context

See `proposal.md` (Why) for motivation. Current state that shapes the approach:

- `AIPortfolioExecutor(broker, allocated_capital)` stores `self.allocated_capital`.
  `execute_rebalance` sets `base_capital = self.allocated_capital` and sizes each target
  as `target_value = base_capital × weight` (whole-share for equities,
  `ai_portfolio/executor.py:399, 546`; fractional for crypto), trading the delta against
  the current position.
- At the rebalance seam (`ai_portfolio/service.py:855`) the executor is constructed with
  `session_row.allocated_capital` — the value frozen at build time, which never tracks
  the session's gains, losses, or fees.
- The session's **current** value already exists:
  `paper_trading/service.py compute_session_value().total_value`
  (`allocated_capital + total_pnl − total_fees + unrealised_total`), which equals the
  current positions' market value plus the derived free cash. This is the same figure the
  KPIs and daily snapshots use, so reusing it keeps sizing and reporting consistent.
- The **build** seam (`:518`) and the **close** seam (`:1012`, `:1351`) also construct the
  executor with `allocated_capital`, but build sizing off allocated capital is correct
  (current value == allocated capital at build) and `execute_close` ignores the base
  entirely (it liquidates in full).

## Goals / Non-Goals

**Goals:**
- Make an automated rebalance allocate the session's **current** equity across its target
  weights, so gains are redeployed and losses are respected each run.
- Reuse the already-computed current-value figure so sizing and reporting stay consistent.

**Non-Goals:**
- No change to the target-weight delta model, guardrail enforcement, crypto/equity
  sizing rules, scheduling, notifications, the order model, or KPIs/valuation.
- No change to build or close sizing.
- Not addressing within-run execution ordering (sells-before-buys); that is a separate
  concern deliberately out of scope here.

## Decisions

### D1 — Rebalance base capital = current marked-to-market value
Size the rebalance against `compute_session_value(session, session_id, broker).total_value`
instead of `session_row.allocated_capital`. Since the normalised weights sum to ~1, the
sum of target position values equals the session's current value (current positions +
cash), so the run deploys the whole current equity across the targets — redeploying gains
and sizing down after losses. *Alternatives:* (a) allocated capital (status quo) —
rejected, it strands gains and over-commits after losses; (b) only free cash as
additional headroom — rejected, it would not rebalance existing positions to their target
*proportions* of current equity, only top up with idle cash.

### D2 — Pass the base per rebalance run, keep build/close unchanged
Make the rebalance base an input to the rebalance path rather than mutating the
executor's stored `allocated_capital`, so `execute_build` keeps sizing off the allocated
capital and `execute_close` is untouched. Concretely, either pass a `base_capital` into
`execute_rebalance` or construct the rebalance executor with the current value; the build
and close seams continue to pass `allocated_capital`. This isolates the behavior change to
the rebalance seam and keeps the build's results identical.

### D3 — Reuse `compute_session_value`, do not recompute
The rebalance already has `session`, `session_id`, and `broker` in scope and already
fetches quotes; call `compute_session_value` once and use its `total_value`. This is the
same mark-to-market the KPIs and snapshots use, so a rebalance and the KPI view agree on
what the session is worth. No new valuation logic is introduced.

### D4 — Marking to market includes unrealised gains (intended)
The current value includes live unrealised P&L, so a position sitting on a large
unrealised gain raises the base and is targeted at a correspondingly larger value — this
is the intended mark-to-market rebalancing behavior, matching how the KPIs already frame
the session. On a down day the base is lower and targets trim accordingly.

### D5 — Accept a negligible within-run fee under-funding
Each rebalance also accrues this run's per-trade fees, which are charged at trade
recording and are therefore not yet netted out of `total_value` at sizing time. The run
can thus target an amount larger than the post-fee equity by roughly this run's fees — a
negligible amount that self-corrects on the next run (the prior run's fees are then netted
in). No special handling; noted for completeness.

## Risks / Trade-offs

- **[Over-commit by this run's unbooked fees]** → D5; negligible and self-correcting.
- **[Sizing now varies with intraday marks]** → intended (D4); a rebalance should target
  the session's current worth. The same mark-to-market already drives the KPIs, so there
  is no new source of truth.
- **[Interaction with `add-weekend-crypto-rebalance`]** → that change (not yet applied)
  stated in its D5 that weekday execution still sizes off `allocated_capital`. This change
  supersedes that for the weekday full-portfolio run: the base becomes current value. The
  two remain consistent — the crypto-only run there sizes against the crypto investable
  budget (crypto market value + unallocated cash), which is itself a slice of current
  value. Whichever is applied second should update the other's wording; no requirement
  conflicts.

## Migration Plan

None. Pure runtime sizing change; no schema change, no Alembic migration, no backfill. The
corrected behavior applies to every session's next rebalance automatically. Rollback is
reverting the rebalance base back to `allocated_capital`.

## Open Questions

None that affect the specs, approach, or task breakdown.
