## Why

When an AI portfolio is built, the build immediately places broker buy orders — with **no market-open guard**. If the build happens while the market is closed, those orders sit at the broker as `SUBMITTED`/`PENDING` and have not filled, yet the build optimistically writes the local ledger as if every order filled at the quote price. The daily rebalance cron then picks the freshly-built session up on its very next run and rebalances it against that optimistic, not-yet-real ledger — "before anything ever happened to those orders." Because the rebalance sizes deltas from the ledger, it can emit adjusting orders (for example sells) against shares the broker has **not actually acquired**, producing rejected or inconsistent trades the moment the market opens.

## What Changes

- The daily rebalance trigger's session selection SHALL **exclude a session whose initial build orders have not all reached a terminal filled/settled status**, and SHALL include it once they have. A session built while the market is closed is therefore skipped by the immediate next rebalance run and joins the run after, once its build buys fill.
- Readiness is gated on **actual broker fill status** (each build order's reconciled `order_status`), not on an elapsed-run or time counter. The trigger SHALL refresh the session's build-order statuses against the broker before deciding, since the separate reconcile cron is not guaranteed to have run first.
- A session with **no build orders to wait on** (an all-cash build, or a build whose orders already filled — e.g. the immediate-fill stub broker) SHALL be immediately eligible, so this never permanently strands a session.
- The trigger SHALL report a deferred session as **skipped** (distinct from "already running"), so a build-closed-market session's outcome is observable.
- No new user-facing configuration: this is automatic, default-on behaviour for every daily-rebalancing session. Manual single-session rebalance is unaffected.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `daily-rebalancing`: The cron-guarded daily rebalance trigger gains a build-order-fill readiness gate on its session selection — a freshly-built session is deferred from daily rebalancing until its initial build orders reach a terminal filled state (confirmed via broker order-status reconciliation), then included.

## Impact

- **Backend — session selection:** `api/routers/ai_portfolio.py` `rebalance_daily` (the `ACTIVE + AI strategy + DAILY_REBALANCING` filter at ~L251-257) gains a readiness check; deferred sessions are reported as skipped alongside already-running ones.
- **Backend — readiness signal:** a `paper_trading`/`ai_portfolio` service helper that, for a session, identifies its initial build orders (via the build event recorded in `session_metadata.build_event_id` / that event's `PaperTrade` rows), reconciles their status against the broker (reusing the existing `reconcile_session_orders`), and reports whether they are all terminal/filled. A session with no such orders is ready.
- **Broker I/O:** reuses the existing `Broker.get_order` reconciliation path; no new broker capability. Under `ALPACA_STUB` (immediate fills) sessions are ready right away, preserving offline/test behaviour.
- **No schema change** anticipated (readiness is derived from existing `PaperTrade.order_status` + build-event linkage), and **no frontend change** (no new config surface).
- **Unaffected:** stop-loss, risk guardrails, technical-indicator strategy, and the build path's own order placement all keep current behaviour.
