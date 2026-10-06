## Context

See `proposal.md` — Why, for the motivation and the live evidence (session `f9db4457`: 38% cash, ten consecutive `partial` rebalances, `ASML.AS` targeted at 15% failing "No price available" every run).

Current rebalance sizing lives in `AIPortfolioExecutor.execute_rebalance` (`backend/src/cadence/ai_portfolio/executor.py`). The relevant flow:

- Target weights are normalized to sum to 1.0 over the AI's `targets` list **once, up front** (`executor.py:484-488`), then optionally guardrail-clamped, then sized against a fixed `net_base = base − reserved_buffer` (`executor.py:493-501`).
- The per-ticker loop (`executor.py:511-560`) sizes each target **independently**: if the broker returns no usable price it records a `TradeResult(executed=False, reason="No price available")` and `continue`s (`executor.py:530-543`); otherwise `_plan_equity` / `_plan_crypto` size the delta.
- `_plan_equity` (`executor.py:802-847`) computes `target_shares = int(net_base * weight / price)`. When the weight's budget is below one share's price, `target_shares == 0`; for a not-held name that is a `delta == 0` → returns `None`, a **silent** no-op (no `TradeResult` recorded at all). `_plan_crypto` (`executor.py:849-901`) is fractional and only strands sub-min-notional deltas.
- Nothing ever redistributes the weight of a skipped/no-op target. Because the normalization and `net_base` are fixed before the loop, a target that fails to execute just leaves its slice of `net_base` unspent → persistent cash. The agent re-selecting the same unexecutable ticker (e.g. `ASML.AS`) makes it permanent.

Candidate assembly for a rebalance happens in `ai_portfolio/service.py` (the rebalance run path that builds the universe handed to the agent). A ticker the broker cannot price is offered to the agent again every run.

Constraints: whole-share equity sizing stays (fractional equities are out of scope); the reserved cash buffer, the guardrail clamp, crypto-only scoping, the `market_open` equity-skip, and the sells-before-buys phasing must all be preserved; this is a behavioral change with no expected DB migration or frontend change.

## Goals / Non-Goals

**Goals:**
- A rebalance deploys the capital its executable targets can absorb instead of stranding the weight of unexecutable targets as cash.
- Unexecutable targets are recorded with an explicit reason (no silent no-ops), so `partial` runs are explainable from `run_stats`.
- Known-unexecutable tickers stop being re-offered to the agent at rebalance time.
- Buffer, guardrails, crypto-only, market-open, and sells-before-buys semantics are unchanged.

**Non-Goals:**
- Fractional equity shares (documented follow-up).
- Changing the agent's target-selection logic beyond excluding known-unexecutable candidates.
- Any change to the build path's sizing beyond what falls out naturally (redeployment is defined at the rebalance seam; build-time behavior may be left as-is unless trivially shared).
- Reworking the guardrail caps (their "remainder stays cash" behavior is intentional and unchanged).

## Decisions

### D1 — Redeploy by iterating the sizing over the executable set, not by one-shot re-normalization

**Chosen:** Determine executability per target (priceable + can fund the minimum tradable amount at the current `net_base` share), then redistribute the unexecutable targets' weight proportionally across the executable targets and re-size. Because redistributing weight can make a previously-affordable boundary case flip, do this as a **bounded fixed-point loop**: recompute the executable set and re-normalize among it until the set is stable (no new target becomes unexecutable) or an iteration cap is hit. Stop deploying once the remaining deployable cash (above the reserved buffer) is exhausted.

**Why:** A single re-normalization pass over "priceable" targets would still strand "too small for one share" cases and could itself create new sub-one-share targets. A bounded loop converges on the set that actually absorbs the capital. Alternative considered — a greedy "fill the largest-weight affordable target with leftover cash" sweep — deploys marginally more but departs from the weight-proportional intent and complicates guardrail interaction; rejected in favor of staying weight-proportional.

**Guardrail interaction:** When `caps` is provided, run the guardrail clamp **after** each redistribution (or clamp the redistributed vector), so redeployed weight still satisfies per-asset / per-asset-class / max-invested caps. Weight that cannot be placed without breaching a cap stays cash — unchanged guardrail semantics.

### D2 — Define "executable" at the executor boundary from data it already has

Executability is decided from the broker quote (already fetched in the loop at `executor.py:530`) and the whole-share / min-notional affordability test already encoded in `_plan_equity` / `_plan_crypto`. No new broker capability is required for the executor-side redeployment. This keeps the change inside `execute_rebalance` and its planners.

**Alternative considered:** pre-querying tradability via a new broker `get_asset` call. Rejected here — that belongs to the separate "verify tradability via Alpaca at add-time" plan; the executor already learns unpriceability from the quote it fetches.

### D3 — Record the "too small for one share" no-op instead of returning a silent `None`

`_plan_equity` (and `_plan_crypto` for sub-min-notional) currently return `None` for the zero/boundary case, which the loop drops without a `TradeResult`. Change the rebalance loop (or the planners' callers) so a target that is skipped for affordability is recorded as `executed=False` with a reason. This satisfies the "Record a rebalance target that cannot be executed" requirement and is what makes redeployment observable in `run_stats`. A genuine `|delta| < 1` **adjustment** of an already-held position at (near) its target is a legitimate no-op and need not be surfaced as a failure — distinguish "already at target" from "could not fund a wanted position."

### D4 — Exclude known-unexecutable tickers during rebalance candidate assembly

In the rebalance candidate assembly in `ai_portfolio/service.py`, filter out tickers known to be unexecutable on the configured brokerage before handing candidates to the agent, so names like `ASML.AS` stop being re-targeted. The exclusion is scoped to *candidate assembly*; it must not change which held positions a rebalance can sell/exit (a held, now-unexecutable position must still be exitable). Signal source for "known unexecutable": start from what the system can already determine (e.g. a broker price/tradability check at assembly time, consistent with how the universe is built); keep it coordinated with — not duplicating — the add-time Alpaca tradability plan.

### D5 — No schema / frontend change

The change is behavioral within the executor and rebalance service. Expected: no Alembic migration, no `api/schemas.py` read-model change, no frontend change. `run_stats.trades` already carries non-executed outcomes, so the newly-recorded skips flow through the existing learning/reporting path with no shape change. Confirm during implementation that no read model needs touching.

## Risks / Trade-offs

- **Over-concentration when guardrails are OFF** → Redeploying freed weight proportionally can push more capital into the highest-weight names (e.g. NVDA). This is the intended effect (deploy the capital) and is bounded by the agent's own weight vector; sessions that want concentration limits can enable guardrails, which are still enforced post-redeployment. Mitigation: proportional (not greedy-into-one-name) redistribution keeps the tilt proportional to the agent's intent.
- **Boundary oscillation in the redeployment loop** → redistributing weight could repeatedly flip a marginal target in/out of the executable set. Mitigation: bounded iteration count with a deterministic stop (set stable, or deployable cash exhausted); on exhaustion, leave residual as cash.
- **Masking genuinely bad agent output** → surfacing/redeploying around unexecutable targets could hide that the agent keeps picking bad tickers. Mitigation: D3 records every unexecutable target with a reason (visible in `run_stats`), and D4 removes the root cause by not re-offering them.
- **Interaction with the no-deployable-cash skip** → the existing "skip a rebalance that can only buy with no deployable cash" requirement must still short-circuit correctly; redeployment only changes how weight maps to executable targets, not whether there is deployable cash. Mitigation: keep the skip check where it is and cover it with a regression test.
- **Crypto-only path** → redeployment must behave within the crypto-only scoped target set and not reintroduce equities. Mitigation: apply redeployment after the existing crypto-only filtering, over the already-scoped targets.

## Migration Plan

Pure behavioral change: deploy the updated backend; no data migration, no backfill. The next scheduled rebalance for each affected session redeploys the previously-stranded cash into executable targets automatically (sizing is against current value, so the idle cash becomes deployable base). Rollback is reverting the code; no state to undo. No frontend coordination needed.

## Open Questions

- Exact signal for "known unexecutable" at candidate assembly (D4): reuse the same price/tradability probe the universe build already performs, versus a lightweight broker check. Resolve during implementation from how `ai_portfolio/service.py` currently assembles the universe — it does not change the specs, the redeployment approach, or the task breakdown.
