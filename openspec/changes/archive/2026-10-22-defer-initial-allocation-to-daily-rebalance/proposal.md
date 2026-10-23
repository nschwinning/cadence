## Why

Building an AI portfolio currently places opening trades immediately: the build
creates the shell and then runs the opening allocation **inline** as an initial
rebalance, so a brand-new portfolio is fully invested within seconds of being
created. A user who expected to "create an empty portfolio and then enroll it
into the daily rebalancing" is surprised to find it already trading. We want the
mental model the user expects to be the actual behavior: a build creates an
enrolled-but-empty portfolio, and the first scheduled daily rebalance performs
the opening allocation.

## What Changes

- **BREAKING (behavioral, for everyone):** A build no longer allocates capital at
  creation. It creates the portfolio and the enrolled paper-trading session
  shell, places **no** opening orders, and does **not** trigger an inline initial
  rebalance. The new session holds 100% cash (its allocated capital) until its
  first scheduled daily rebalance.
- The session's opening allocation is produced by its **first scheduled daily
  rebalance**, through the exact same rebalance path as every later rebalance
  (same prompt, trend gate, fundamentals, guardrail clamp, cash buffer,
  unexecutable-weight redeploy, sells-before-buys). Timing moves; the allocation
  mechanism is unchanged.
- The scheduled-rebalance **readiness gate** is adjusted so a never-allocated
  session (one with no recorded initial/opening rebalance) is treated as **ready**
  — it is allocated on the first scheduled run rather than deferred as
  "awaiting build fill." Once that first rebalance runs, subsequent scheduled
  runs gate on its settled orders exactly as today.
- Mandatory daily-rebalancing enrollment is unchanged: every built session is
  still enrolled; there is still no opt-out. A crypto-scope session is allocated
  on the weekend crypto cadence; an all-equity session built while the market is
  closed is allocated on the next scheduled run.
- **Frontend:** the build card no longer implies trades happened. On successful
  build it communicates that the portfolio was created and enrolled and will be
  allocated on its next daily rebalance.
- The immediate-allocation behavior is **removed, not merely defaulted off** — a
  per-build opt-in to allocate immediately is explicitly out of scope (the user
  chose a flat default). It could be re-added later if wanted.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `ai-paper-trading`: the build/opening-allocation requirements change — a build
  creates an enrolled empty session and places no opening orders or inline
  rebalance; the opening allocation is produced by the session's first scheduled
  daily rebalance; the readiness gate admits a never-allocated session so the
  first scheduled run allocates it. (Replaces the current "Opening allocation runs
  through an initial rebalance" requirement; amends "Build an AI portfolio and
  execute it as paper trades" and "Poll AI portfolio build status".)
- `app-shell`: the AI portfolio build card communicates on completion that the new
  portfolio is created and enrolled and will be allocated on its next daily
  rebalance, rather than implying opening trades were placed.

## Impact

- Backend: `ai_portfolio/flows/build.py` (drop the inline initial-rebalance
  creation + `run_rebalance_event` call); `ai_portfolio/events.py`
  (`build_orders_settled` readiness gate treats a never-allocated session as
  ready); cron fan-out `api/routers/ai_portfolio.py` (`rebalance_daily` /
  `rebalance_crypto_daily`) targeting is unchanged but now picks up empty
  sessions on their first run.
- Frontend: `pages/portfolios/BuildAIPortfolioCard.tsx` (+ its Vitest test) for
  honest post-build copy.
- No schema change expected (no migration): the build simply stops writing
  `session_metadata["initial_rebalance_event_id"]`, and the gate keys off its
  absence.
- Dead code: the inline `create_rebalance_event` + `run_rebalance_event` call in
  `build.py` is removed; the already-dead `execute_build` / `agent.build` /
  `build_ai_portfolio` / build prompt remain dead and untouched.
- Out of scope: any opt-in "allocate immediately" toggle; the rebalance
  agent/prompt/sizing/guardrails/cash-buffer/redeploy logic; the cron schedule
  times; the plain `POST /api/v1/portfolios` endpoint; notifications; archiving.
