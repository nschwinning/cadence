## Context

See proposal.md — Why. Build and rebalance are two allocation paths today:

- **Build** (`ai_portfolio/flows/build.py::run_build_event`): `agent.build()` → create portfolio → `paper_service.create_session()` → `executor.execute_build()` → record trades + run. Runs on a single-worker `ThreadPoolExecutor` (`background.py`, `max_workers=1`).
- **Rebalance** (`ai_portfolio/flows/rebalance.py::run_rebalance_event`): reads the frozen session, values it (`compute_session_value`), builds holdings from the ledger, assembles scoped candidates (trend gate / fundamentals), calls `agent.rebalance()`, then `executor.execute_rebalance()` (guardrail clamp, cash buffer, redeploy, sells-before-buys, sizing against current value). Already handles an **empty ledger** and a **buy-only** run (`skipped_noop`, market-closed skip).

`build_orders_settled` (`ai_portfolio/events.py`) gates the scheduled daily job: it reads the build event's trades (via `session_metadata["build_event_id"]`) and defers the session until those orders reach a terminal broker state. A session whose build placed **no** orders is reported ready immediately.

The daily/crypto-daily cron (`api/routers/ai_portfolio.py`) targets active `DAILY_REBALANCING` AI sessions and calls `build_orders_settled` before `start_rebalance`.

## Goals / Non-Goals

**Goals:**

- One allocation path: the opening allocation *is* a rebalance, so every rebalance-only enhancement (trend, fundamentals, guardrail clamp, cash buffer, redeploy, sells-before-buys, live-value sizing) applies from day one, for all portfolios.
- No special-casing of the first allocation — the initial rebalance differs from any other only in having no open positions yet.
- Manual sessions are allocated at creation; daily sessions are allocated at creation and remain enrolled in the scheduled job.

**Non-Goals:**

- No change to the rebalance algorithm itself (`run_rebalance_event` / `execute_rebalance` are reused as-is).
- No migration / schema change; no new event kind.
- No change to the daily/crypto-daily cron targeting rules.
- Not deleting `agent.build()` / `executor.execute_build()` / the build prompt in this change beyond removing their call sites (see D5) — they become dead code; physical deletion may follow.

## Decisions

### D1 — Build creates a shell; the opening allocation is a separate initial rebalance event driven inline

`run_build_event` keeps everything up to and including `create_portfolio` + `create_session` (freezing all opt-ins, prompt versions, benchmark, metadata) and setting `event.session_id` / `event.portfolio_id`. It then **removes** `agent.build()`, `executor.execute_build()`, and `_record_trades`, and instead creates a rebalance event for the new session and runs `run_rebalance_event(...)` for it.

- **Why a separate rebalance event (not re-driving the build event as a rebalance):** `run_rebalance_event` is written against a rebalance event (sets status, records a run with trigger `ai_rebalance`, finishes the event). Reusing it verbatim against its own event keeps the rebalance path untouched and keeps the two concerns cleanly separated — the build event records "shell created + opening allocation triggered"; the rebalance event records the opening trades/run. This preserves the build-status polling contract shape (the build event still reaches a terminal status) while the opening trades live where every other allocation's trades live: on a rebalance run in the session's history.
- **Alternative considered — extract a shared `_allocate()` core and have the build event carry the opening trades.** Rejected for this change: it means refactoring `run_rebalance_event`'s core and conflating event kinds (a "build" event carrying rebalance trades). The separate-event approach is a smaller, lower-risk diff and matches "the opening allocation is a rebalance."

### D2 — Drive the initial rebalance DIRECTLY, not through `job_runner.start_rebalance`

The build job already runs on the single-worker pool (`max_workers=1`). Submitting the initial rebalance via `start_rebalance` (which `executor.submit(...)`s onto the same pool) would **deadlock** — the build job would block waiting for a task that cannot start until the build job returns. Therefore the build flow calls `run_rebalance_event(session, rebalance_event_id, agent, broker, provider)` directly, synchronously, in the same worker thread, after committing the shell. (No notifier on the initial rebalance — the build path is silent, like a manual rebalance; a daily-cron rebalance later notifies.)

- Create the rebalance event with the existing `service.create_rebalance_event(session, session_id)` so the in-flight guard and run plumbing behave normally.

### D3 — The readiness gate follows the opening allocation to the initial rebalance event

Because the build event now places no orders, `build_orders_settled` would report every freshly built session "ready" immediately — but its *opening* orders (on the initial rebalance) may still be unsettled, so the scheduled daily job could rebalance on unsettled opening holdings. Fix: record the initial rebalance event id on the session (e.g. `session_metadata["initial_rebalance_event_id"]`) and have `build_orders_settled` read **that** event's trades instead of (or, for legacy sessions, falling back to) the build event's. Legacy sessions (built before this change, no `initial_rebalance_event_id`) keep reading the build event, so their behavior is unchanged.

- **Why metadata, not a new column:** avoids a migration; mirrors how `build_event_id` is already carried in `session_metadata`.

### D4 — Market-closed / no-op opening allocation is deferred, not forced

The initial rebalance runs the normal rebalance guards. An all-equity session built while the equities market is closed records a skipped run and places nothing (no special-casing — per the user's direction). The allocation is then produced at the next opportunity: the scheduled daily job (daily sessions), the weekend crypto cadence (crypto sleeve), or a later manual rebalance. A crypto-scope or `both`-scope session can still allocate its crypto sleeve immediately since crypto trades 24/7.

- **Consequence to accept:** a *manual* all-equity session built while the market is closed is not allocated until the operator triggers a manual rebalance once the market reopens. This is the deliberate "no special-casing" trade-off; forcing an out-of-hours opening fill would be a special case the user explicitly ruled out.

### D5 — `execute_build` / `agent.build()` / build prompt become dead code

Removing the build-time allocation leaves these unreferenced. This change deletes their **call sites** in `build.py` and updates/removes build-executor tests that asserted execute-build sizing. The now-unused `AIPortfolioExecutor.execute_build`, `AIPortfolioAgent.build`, and the build prompt are left in place (or removed if trivially safe) — flagged as dead code for a follow-up cleanup so this change stays focused on the flow switch.

## Risks / Trade-offs

- **[Longer build jobs]** The build job now also runs a full rebalance (an agent call + order submission) inline → builds take as long as a build + a rebalance. → Acceptable: it is the same total work that previously happened across build + first rebalance, now consolidated; the endpoint already returns 202 immediately and the client polls.
- **[Readiness-gate regression]** If D3 is missed, the daily job could trade on unsettled opening holdings. → Covered by an explicit requirement + test; legacy fallback keeps old sessions correct.
- **[Build-status UX]** Clients that read opening trades off the build event's actions will see none. → The opening trades are on the session's initial rebalance run; verify the build card only polls to completion and navigates (no `app-shell` spec change expected). If a user-visible copy references build-event trades, handle it under `app-shell`.
- **[Empty-universe / no-candidate opening]** A build whose opening rebalance finds nothing to buy records a skipped/no-op run rather than failing. → Matches existing rebalance no-op behavior; the shell still exists and can be rebalanced later.
- **[Two events per build]** Slightly more event rows per build. → Negligible; mirrors the natural build-then-rebalance lifecycle.

## Migration Plan

- No data migration. Existing sessions are unaffected (they already hold positions; their `build_orders_settled` legacy path is preserved).
- Deploy is a pure code change. Rollback is reverting the flow change; no schema to undo.
- No backfill: the `initial_rebalance_event_id` metadata key only appears on sessions built after deploy.
