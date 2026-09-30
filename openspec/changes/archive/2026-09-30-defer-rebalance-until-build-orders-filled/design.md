## Context

See `proposal.md` — Why. Current state of the relevant seams (verified against the code):

- **Build places orders with no market guard.** `AIPortfolioExecutor.execute_build` (`ai_portfolio/executor.py`) unconditionally calls `broker.buy` per holding; unlike `execute_rebalance` it takes no `market_open` flag. A `TradeResult` is marked `executed=True` whenever `broker.buy` returns, independent of fill state. With the immediate-fill stub broker orders come back `FILLED`; with real Alpaca a market order placed while closed comes back `new`/`accepted` → `SUBMITTED` (or `pending_new` → `PENDING`), `filled_price` null.
- **The ledger is written optimistically.** `_record_trades` (`ai_portfolio/service.py`) applies every `executed` build trade to the session ledger via `apply_fill_to_ledger` regardless of `order_status`. So a build during closed hours leaves a fully-populated ledger while the broker orders are still unfilled.
- **Daily rebalance selection is fill-blind.** `rebalance_daily` (`api/routers/ai_portfolio.py`) selects `list_sessions(status=ACTIVE)` filtered to `schedule_mode == DAILY_REBALANCING` and `strategy_key == AI_STRATEGY_KEY`, then starts one background rebalance per target, skipping only those with an in-flight rebalance (`get_inflight_rebalance_event`). It never consults build recency or order fill status. The rebalance itself reads positions from the local ledger (the "source of truth"), so it trusts the optimistic state.
- **Reconciliation already exists but is decoupled.** `reconcile_session_orders` (`paper_trading/service.py`) re-fetches every non-terminal trade with an `order_id` via `broker.get_order`, writes back `order_status`/`filled_price`/`filled_at`, and repairs ledger cost basis. It is invoked by `POST /sessions/{id}/reconcile` and the batch `POST /reconcile-daily` cron — with **no ordering guarantee** relative to `/rebalance-daily`.
- **Build linkage.** A session's build event id is stored in `session_metadata` JSONB as `build_event_id` at build time; the build's `PaperTrade` rows carry the `session_id`. `PaperTrade.order_status` is the per-order fill state.

## Goals / Non-Goals

**Goals:**
- Gate the daily rebalance trigger's per-session selection on a *build-order-fill readiness* signal derived from real broker order status.
- Refresh that status against the broker at decision time so the gate does not depend on `/reconcile-daily` having run first.
- Keep the signal robust: a session with nothing to wait on is ready; terminal-but-not-filled orders (cancelled/rejected) do not strand it.
- Report a deferred session as *skipped*, distinct from *already running*.

**Non-Goals:**
- Adding a market-open guard to `execute_build`, or changing how the build places orders or writes the ledger. (A separate concern; out of scope here.)
- Reconciling or altering the rebalance's own position sourcing beyond the readiness gate.
- Any new persisted column, migration, config env, or frontend surface.
- Governing manual single-session rebalance — only the daily cron trigger.

## Decisions

**1. Gate on reconciled build-order fill status, computed at trigger time.**
A new service helper — `session_build_orders_settled(db, session, broker) -> bool` (in `paper_trading/service.py`, or an `ai_portfolio/service.py` wrapper if the build-event lookup lives there) — resolves the session's initial build orders, reconciles them against the broker, and returns whether all are terminal-filled (or there are none to wait on). `rebalance_daily` calls it per candidate and moves not-ready sessions into the skipped list.
- *Why over a time/counter heuristic:* the user explicitly chose "build orders filled" over "one rebalance elapsed." Fill status is the true readiness condition; a timer would either rebalance too early (fast fills unnecessarily delayed, or slow fills still not filled) or add config nobody asked for.
- *Why reconcile at trigger time rather than trust stored status:* `/reconcile-daily` is not guaranteed to run before `/rebalance-daily`, so stored `order_status` may be stale `SUBMITTED`. Reconciling first makes the gate correct regardless of cron ordering, and reuses the existing, already-tested `reconcile_session_orders` (which also repairs cost basis as a beneficial side effect right before the rebalance reads the ledger).

**2. Identify "initial build orders" via the build event.**
Resolve the build event from `session_metadata["build_event_id"]`, then its `PaperTrade` rows (the build's trades). Readiness = every such trade with an `order_id` is in a terminal filled state; trades without an `order_id`, or a build with no trades, contribute nothing to wait on. This reuses existing linkage — no schema change.
- *Alternative considered:* a new `build_settled_at` timestamp column set by reconciliation. Rejected for this change: it adds a migration and backfill for a signal we can already derive, and the derived check is idempotent and cheap (one reconcile call per candidate at cron time).

**3. "Ready when nothing to wait on."**
No build orders, or all terminal, ⇒ ready. Terminal non-filled (cancelled/rejected) counts as settled-not-pending so a partially-rejected build can still rebalance. This guarantees the gate can never permanently strand a session.

**4. Skip reporting stays in the existing triggered/skipped response shape.**
Deferred sessions join the skipped list. If the response distinguishes reasons, tag build-order deferral distinctly from already-running; otherwise at minimum include the id among skipped. No new endpoint or response contract beyond what the trigger already returns.

## Risks / Trade-offs

- **Extra broker calls at cron time** (one reconcile per candidate) → Mitigation: reconcile only touches each session's *non-terminal* build trades (already the case in `reconcile_session_orders`); once a session's builds are filled the reconcile is a cheap no-op, and sessions built long ago have nothing non-terminal to fetch. Bounded by the number of enrolled sessions.
- **Broker unreachable during reconcile** → Mitigation: treat a reconcile failure as "not ready" and skip (defer) the session for that run rather than rebalancing on unverified state; it will be retried next run. Fail safe toward *not trading*.
- **A genuinely stuck build order** (never fills, never cancels) would keep a session deferred indefinitely → Accepted: that is the correct behaviour (do not rebalance a portfolio whose real positions were never established); it surfaces as a persistently-skipped session, and the operator can cancel/reconcile the order to unblock. The terminal-non-filled rule already prevents cancelled/rejected orders from causing this.
- **Immediate-fill stub** makes every session ready at once → intended; preserves current offline/test behaviour so existing daily-rebalance tests are unaffected except where they assert the new deferral explicitly.

## Migration Plan

No data migration. Behaviour is derived at runtime from existing columns and is default-on. Rollback is reverting the code; no schema or config to undo. Existing sessions whose builds long since filled are immediately ready, so the gate is a no-op for them.
