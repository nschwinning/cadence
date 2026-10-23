## Context

See proposal.md — Why. Today `ai_portfolio/flows/build.py::run_build_event` creates
a shell portfolio + enrolled session, then — inline, within the build job —
creates a rebalance event, records its id as
`session_metadata["initial_rebalance_event_id"]`, and calls `run_rebalance_event`
directly to produce the opening allocation. This is the `route-initial-allocation-
through-rebalance` design: the opening allocation flows through the standard
rebalance path so every rebalance-only enhancement applies to it.

The scheduled-rebalance **readiness gate** (`events.py::build_orders_settled`,
called by the `rebalance_daily` / `rebalance_crypto_daily` cron fan-out) exists to
stop a scheduled rebalance from running while a freshly built session's **opening
orders** are still mid-flight. It resolves the opening event as
`metadata["initial_rebalance_event_id"] or metadata["build_event_id"]`, reconciles
the session's orders against the broker, and waits until every trade on that event
reaches a terminal order status. A session with no resolvable opening event, or
whose opening event recorded **zero** orders, is already reported **ready**.

Three generations of sessions coexist and must all keep working:
1. **Ancient** — the build event itself placed the opening orders (pre-`route-
   initial-allocation-through-rebalance`). Orders live under `build_event_id`.
2. **Recent** — the inline initial rebalance placed the opening orders. Orders live
   under `initial_rebalance_event_id`.
3. **New (this change)** — the build places no orders at all and records no
   `initial_rebalance_event_id`. The opening allocation happens on the first
   scheduled daily rebalance.

## Goals / Non-Goals

**Goals:**
- A build creates an enrolled-but-empty session (100% cash) and places no orders /
  triggers no inline rebalance.
- The opening allocation is produced by the first scheduled daily rebalance,
  through the unchanged standard rebalance path.
- All three session generations remain correct through the readiness gate.
- No schema change / no migration.

**Non-Goals:**
- Any opt-in "allocate immediately" control (removed, not defaulted off).
- Touching rebalance agent/prompt/sizing/guardrails/cash-buffer/redeploy logic.
- Changing the cron schedule times or the cron targeting query.
- Removing the now-dead `execute_build` / `agent.build` / `build_ai_portfolio` /
  build prompt (left dead and untouched).

## Decisions

### D1 — Build stops creating + running the inline initial rebalance
Remove the `create_rebalance_event` + metadata write + `run_rebalance_event` block
from `run_build_event`. The build keeps creating the shell portfolio and the
enrolled session, sets `session_metadata` **without** `initial_rebalance_event_id`,
and finishes the build event with no trades (as it already does — `actions_taken`
reflects shell creation only). The newly built session therefore holds 100% cash
until a scheduled run allocates it.

_Alternative considered:_ keep creating the rebalance event but defer its
execution to the cron. Rejected — it reintroduces a half-allocated marker in
metadata and complicates the gate for no benefit; the cron already produces a fresh
rebalance event when it runs.

### D2 — The readiness gate needs no behavioral change; only intent clarified
A new-flow session has `build_event_id` present (the fallback) but **zero** trades
recorded against it, so `build_orders_settled` already returns `True` — the session
is ready on its first scheduled run. Ancient sessions still have real orders under
`build_event_id` and keep waiting; recent sessions still wait on
`initial_rebalance_event_id`. The existing trade-count check is exactly what
distinguishes a never-allocated session (zero orders → ready) from an ancient one
(orders → wait), so **no new branch is required**. The change is limited to
updating the gate's docstring/comments (they currently claim new sessions record
`initial_rebalance_event_id`) and adding a regression test for the new-flow case.

_Alternative considered:_ short-circuit to `ready` before the broker reconcile when
no `initial_rebalance_event_id` is present. Rejected for this change — it would skip
the reconcile for ancient sessions too (which legitimately need it) unless guarded
by the same zero-trades check the code already performs after reconcile. The
wasted reconcile on an order-less session is a harmless no-op; keeping the proven
logic is lower-risk. (Noted as a possible future micro-optimization.)

### D3 — Opening allocation = the first scheduled rebalance, unchanged path
The weekday path needs no new code: `rebalance_daily` already targets `ACTIVE` +
`DAILY_REBALANCING` + AI-strategy sessions and runs `run_rebalance_event`, which
sizes against current value (equal to allocated capital when there are no open
positions) with no sells. The cron targeting query is left untouched.

The **weekend crypto path needed one narrow fix**. `run_rebalance_event`'s
crypto-only mode skips before consulting the agent when the session holds/targets no
crypto (`any_crypto` False — the "holds no crypto to rebalance" guard). Under the old
inline flow the build pre-populated the portfolio picks and opening holdings, so that
guard never fired for a crypto-scope session. A deferred-allocation empty shell has
**no positions and no portfolio picks**, so the guard would skip it and strand a
crypto-scope session empty over the weekend — contradicting the spec scenario "Crypto
session allocated on the weekend cadence". Fix: in crypto-only mode, treat an empty
shell (no ledger, no portfolio picks) whose configured scope admits crypto as
crypto-involved so the run opens the crypto sleeve from cash. The change is scoped to
the never-allocated empty shell — established sessions' weekend behavior is unchanged,
and the downstream "no free cash to buy crypto" guard still skips a cashless shell.

### D4 — Frontend sets honest expectations
`BuildAIPortfolioCard` build-status handling stops implying trades were placed. On a
successful build it shows copy to the effect of "Portfolio created and enrolled —
it will be allocated on its next daily rebalance," and renders no "added N assets" /
opening-trades summary. Covered by an updated Vitest test.

## Risks / Trade-offs

- **[Empty portfolio looks "broken" to a user who refreshes immediately]** → The
  build card copy (D4) and the session detail (cash, no holdings) make the empty-
  then-allocated lifecycle explicit; this is the behavior the user asked for.
- **[Allocation latency — a portfolio built just after a cron run waits until the
  next scheduled run]** → Accepted and documented in the spec; it is the intended
  "enroll into daily rebalancing" model. Crypto scope can allocate on the weekend
  cadence; an all-equity session built while the market is closed allocates on the
  next open run.
- **[Gate regression across the three session generations]** → D2 keeps the proven
  trade-count logic; tests assert: new-flow session (build_event_id, no initial id,
  no trades) → ready; ancient session (orders on build_event_id, not settled) →
  deferred; recent session (orders on initial_rebalance_event_id, not settled) →
  deferred.
- **[Dead code left behind]** → `execute_build` / `agent.build` /
  `build_ai_portfolio` / build prompt were already dead; this change only removes
  the inline-rebalance call. No new dead code of consequence beyond that.

## Migration Plan

No data migration. Deploy is code-only. Existing ancient/recent sessions are
unaffected (their metadata and gate behavior are unchanged). Rollback is reverting
the code; no schema state to undo. Any session built on the new code before a
rollback would simply have its opening allocation produced by the (restored) inline
path on... — not applicable, since rollback restores inline build for *future*
builds; an already-empty new-flow session would be allocated by its next scheduled
rebalance regardless of code version, because the empty session is ready either way.
