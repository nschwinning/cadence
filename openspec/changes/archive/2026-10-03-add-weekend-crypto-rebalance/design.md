## Context

See `proposal.md` (Why) for motivation. Current state that shapes the approach:

- The daily rebalance is triggered by `POST /ai-portfolio/rebalance-daily`
  (`api/routers/ai_portfolio.py`), guarded by `require_valid_cron_token`, and runs
  per-session in the background via the job runner. A busybox `crond` sidecar in
  `docker-compose.yml` calls it on `REBALANCE_SCHEDULE "35 9 * * 1-5"` (Mon–Fri).
- The rebalance run (`ai_portfolio/service.py run_rebalance_event`) reads the
  session's asset scope from metadata (`asset_types`), builds a `scoped_universe`
  and candidate list, and early-returns a SKIPPED run only when the equities market
  is closed **and** no crypto is involved (`_involves_crypto`). Otherwise it invokes
  the agent and runs `executor.execute_rebalance(..., market_open=...)`, which skips
  equities when the market is closed but trades crypto.
- `account_summary` passed to the agent uses `broker.get_account_info().buying_power`
  — the **global, shared** broker's cash, not the session's. The executor
  (`ai_portfolio/executor.py`) sizes every trade off `self.allocated_capital`.
- The per-session free cash already exists as
  `paper_trading/service.py compute_session_value().cash_value`
  (`allocated_capital + total_pnl − total_fees + unrealised − positions_value`),
  stored on daily snapshots and computed inside `session_kpis`, but not surfaced on
  the live KPI read and not passed to the agent.
- The rebalance prompt is a DB-versioned `RebalancePrompt` row; the active prompt is
  the highest version, and each session freezes the active version at build time
  (`rebalance_prompt_version`).

## Goals / Non-Goals

**Goals:**
- A cron-triggered crypto-only rebalance that can run on weekends, touching only the
  crypto sleeve of each session and sizing it against a correct per-session budget.
- Give the agent the session's real free cash; expose that free cash in the KPIs/UI.

**Non-Goals:**
- No change to the weekday full-portfolio run's scheduling or its equity handling.
- No change to the order model (still market/day).
- No automatic weekend rebalance for equities (the equities market is closed).
- No new per-snapshot storage of the crypto budget; it is derived at run time.

## Decisions

### D1 — Separate endpoint, not a flag on the daily trigger
Add `POST /ai-portfolio/rebalance-crypto-daily` as a sibling of `rebalance-daily`,
reusing the same token guard, active-session targeting, already-running skip, and
build-settled deferral, but starting a crypto-only job. *Alternative:* a
`?crypto_only=true` query param on the existing endpoint. Rejected because the two
have different cron schedules and different skip semantics (crypto-only also skips
no-crypto sessions before the agent), and a distinct endpoint keeps the cron scripts
and logs unambiguous.

### D2 — Crypto-only is a run-time mode, not a per-session setting
The crypto-only behavior is driven entirely by the endpoint/job, which passes a
`crypto_only` flag down through `run_rebalance_event`. In that mode the run intersects
`allowed_categories` with `{CRYPTO}` regardless of the session's own
`asset_types`. *Alternative:* a per-session "crypto weekend" opt-in column. Rejected
as unnecessary — every daily-rebalancing session with crypto should be tended on
weekends; no extra config is warranted.

### D3 — Exclude held equities from the delta, don't just drop them from candidates
The executor computes buy/sell deltas over the **union of held and target tickers**,
so merely removing equities from the candidate/target set would make held equities
have an implicit target weight of 0 and get **sold**. The crypto-only mode must
therefore restrict *both* the candidate/target set *and* the set of current holdings
under consideration to crypto, so equities are never assigned a target and never
traded. This is the single most important correctness point of the change.

### D4 — Crypto budget = crypto positions' market value + unallocated cash
In crypto-only mode the executor sizes crypto weights against a
`crypto_budget` computed by the service as `Σ(crypto position market value) +
compute_session_value().cash_value`, passed into `execute_rebalance` as the base
capital for this run instead of `allocated_capital`. The agent's returned crypto
weights (normalised to ~1.0) then map onto the crypto sleeve plus idle cash, never
onto equity capital. *Alternative A:* size off `allocated_capital` (status quo) —
rejected, it would pour all capital into crypto for mixed sessions. *Alternative B:*
free cash only (no rotation between cryptos) — rejected per product decision; we want
the sleeve rebalanced and idle cash deployable.

### D5 — Feed session-derived cash to the agent for all rebalances
`account_summary` will carry the session's own `cash_value` instead of the shared
broker's `buying_power`; the crypto-only run additionally includes the `crypto_budget`.
This also corrects the latent global-cash bug for the weekday run (the agent gets
accurate free cash). It is reasoning input only — weekday execution still sizes off
`allocated_capital`, so weekday sizing is unchanged; only the agent's information
improves.

### D6 — Crypto prompt is a separate versioned prompt family (a `kind` discriminator)
The crypto-only run needs its own prompt, but it cannot simply be "the next
`RebalancePrompt` version": the active prompt is the highest version, and making the
crypto prompt the highest version would cause newly-built sessions to freeze *it* for
their **weekday** runs too. Decision: add a `kind` discriminator to the prompt record
(values `rebalance` and `crypto_rebalance`), with versions monotonic **per kind** and
the active prompt being the highest version within a kind. Seed `crypto_rebalance`
v1. Each session freezes a crypto prompt version at build time in a new
`crypto_rebalance_prompt_version` column, mirroring the existing freeze exactly
(backfilled for pre-existing sessions to the seeded active crypto version, kept
non-nullable so there is no runtime fallback). The crypto-only run loads the session's
frozen crypto prompt and fails cleanly if it is missing. *Alternative:* resolve the
active crypto prompt at run time with no per-session freeze — lighter (no column,
no build-flow/read change) but inconsistent with the existing reproducibility model;
rejected for the "clean" option the user chose, but noted as the fallback if the
schema change is deemed too heavy during apply.

### D7 — Reuse readiness, reconciliation, and notifications
The crypto-only trigger reuses the build-orders-settled deferral and the existing
order-reconciliation path (crypto fills immediately under the stub; real Alpaca crypto
is GTC and is covered by reconciliation). It reuses the daily-rebalance notification
path, labelling the message as a crypto-only run. No spec change to notifications or
reconciliation is needed — the behavior is the same kind of cron-triggered rebalance.

### D8 — KPI/UI: reuse the already-computed `cash_value`
`session_kpis` already calls `compute_session_value`, so exposing unallocated cash is
a matter of adding a field to `PaperTradingSessionKpisRead` and a tile in the session
detail view; no new computation or storage.

## Risks / Trade-offs

- **[Selling equities by accident in crypto-only mode]** → D3: restrict both targets
  and considered holdings to crypto; add a test asserting a mixed session's equity
  positions are untouched by a crypto-only run.
- **[Shared stub broker cash is global, not per-session]** → the agent now reasons
  with per-session `cash_value`, but the stub broker's buying-power enforcement is
  still global; this is pre-existing and unchanged. Crypto buys are sized against the
  crypto budget, keeping them within the session's own capital.
- **[Prompt schema change touches an append-only versioned table]** → the `kind`
  column is additive with a default of `rebalance` for existing rows; the new
  `crypto_rebalance` family starts at v1. Migration is forward-compatible and
  round-trippable.
- **[Weekday agent now sees different cash figure]** → D5; execution is unchanged
  (sizing still uses `allocated_capital`), so the only effect is better agent
  information. Covered by a test asserting `account_summary` carries session cash.
- **[Weekend run still invokes the LLM per crypto-holding session]** → accepted cost;
  no-crypto sessions short-circuit before the agent, bounding the spend.

## Migration Plan

1. Alembic migration: add `kind` to the rebalance-prompt table (default `rebalance`
   for existing rows); seed `crypto_rebalance` v1; add non-nullable
   `crypto_rebalance_prompt_version` to the session table, backfilled to the seeded
   active crypto version. Single linear head; round-trip verified
   (`upgrade head` / `downgrade`), `alembic check` clean.
2. Deploy backend (new endpoint + crypto-only run path).
3. Add the `crypto` cron schedule + `crypto-rebalance.sh` to `docker-compose.yml`
   (default `CRYPTO_REBALANCE_SCHEDULE "35 9 * * 6,0"`, `America/New_York`), document
   in `.env.example` and `README.md`, add a manual-trigger helper under `scripts/`.
4. Deploy frontend (unallocated-cash KPI tile).
- **Rollback:** remove the cron schedule (weekend runs stop); the endpoint and prompt
  family are inert when not called. The migration is reversible.

## Open Questions

None that affect the specs, approach, or task breakdown. (If the prompt schema change
is judged too heavy at apply time, D6's run-time-resolution fallback can be chosen
without changing any requirement — the spec only mandates that the crypto-only run use
a versioned crypto-scoped prompt and fail cleanly when it is missing.)
