## Why

Building a portfolio and rebalancing it are two separate allocation paths today: a build runs `agent.build()` + `executor.execute_build()`, while a rebalance runs `agent.rebalance()` + `executor.execute_rebalance()`. Every allocation improvement we have shipped lives on the rebalance path only — the risk-guardrail clamp, the reserved cash buffer, the unexecutable-weight redeploy, sells-before-buys, sizing against the session's live value, and (most recently) the company-fundamentals and trend context. None of them touch the opening allocation. So a freshly built portfolio is allocated by an older, thinner code path and does not benefit from any rebalance-only enhancement until its *second* allocation. This divergence is a standing source of bugs (the build executor re-derives sizing that the rebalance path already solved) and makes every new rebalance feature silently skip day one.

Unifying on a single allocation path fixes this once: if the opening allocation *is* a rebalance, then every present and future rebalance enhancement applies from the first dollar deployed, for **all** portfolios — not only the ones that opted into a particular feature.

## What Changes

- **BREAKING (internal flow):** A build SHALL no longer allocate capital. `run_build_event` creates the portfolio and the paper-trading session shell, freezes the session's opt-ins (asset scope, risk profile, trend, stop-loss, guardrails, learning feedback, fundamentals, benchmark, frozen prompt versions), and places **no** opening orders. `agent.build()` and `executor.execute_build()` are removed from the flow (and become dead code).
- The opening allocation SHALL be produced by an **initial rebalance** that the build triggers inline at creation, through the standard rebalance path — so the trend gate, company fundamentals, the risk-guardrail clamp, the reserved cash buffer, the unexecutable-weight redeploy, sells-before-buys, and sizing-against-current-value all apply to the opening allocation exactly as they do to any later rebalance.
- The initial rebalance SHALL be identical to a normal rebalance; the only difference is that there are no open positions yet, so the session's current value equals its allocated capital and there are no sells to place. There is **no** special-casing of the first allocation — it reasons off the same inputs every rebalance does (free cash + open positions + total available value, gains included).
- The initial rebalance SHALL run regardless of the session's schedule mode, so a **manual** session is allocated at creation and does not sit empty.
- A **daily-rebalancing** session SHALL additionally remain enrolled in the scheduled daily rebalance job; because it now has no unsettled build orders, it becomes eligible for the first scheduled run immediately.
- The build-order-settle readiness gate (which defers a scheduled rebalance until a freshly built session's opening orders have settled) SHALL follow the opening allocation to the **initial rebalance** event rather than the build event, preserving the guarantee that a scheduled rebalance never trades on unsettled opening holdings.
- The build-status read SHALL report the build event as the shell-creation step and reference the triggered initial rebalance; the opening trades SHALL be recorded on the initial rebalance run (visible in the session's run history).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ai-paper-trading`: the "Build an AI portfolio and execute it as paper trades" requirement changes — a build creates the portfolio + session shell and places no opening orders; the opening allocation is produced by an initial rebalance run through the standard rebalance path. The "Poll AI portfolio build status" requirement changes — the build event is the shell-creation step and references the initial rebalance that carries the opening trades. A new requirement specifies the inline initial rebalance (runs regardless of schedule mode; identical to a normal rebalance with no open positions; daily sessions also stay enrolled and become eligible immediately) and the readiness gate following the opening allocation to the initial rebalance event.

## Impact

- **Backend flows:** `ai_portfolio/flows/build.py` (remove the agent-build + execute-build + build-trade recording; create shell, then drive an initial rebalance inline). `ai_portfolio/flows/rebalance.py` reused unchanged for the opening allocation (it already handles an empty ledger and a buy-only run).
- **Background worker:** the initial rebalance must be driven **directly** within the build job, not re-submitted through the single-worker job runner pool (that would deadlock); `ai_portfolio/background.py` / `service.py` wiring.
- **Readiness gate:** `ai_portfolio/events.py::build_orders_settled` (and the session metadata it reads) must track the initial rebalance's orders instead of the build event's; daily/crypto-daily cron targeting in `api/routers/ai_portfolio.py` is otherwise unchanged.
- **Dead code:** `agent.build()`, `executor.execute_build()`, and the build prompt become unused; this change removes their call sites (final deletion of the now-unreferenced methods may follow).
- **No migration / no schema change** expected (reuses existing session columns and event kinds). No frontend behavior change is required if the build card already polls to completion and navigates to the session; any build-card copy referencing "opening trades on the build event" is reviewed under `app-shell` only if it turns out to be user-visible.
- **Tests:** build-flow tests shift from asserting execute-build trades to asserting a shell + an initial rebalance that produced the opening trades; readiness-gate tests updated to follow the initial rebalance.
