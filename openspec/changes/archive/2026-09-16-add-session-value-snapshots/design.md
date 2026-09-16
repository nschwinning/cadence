## Context

See proposal.md — Why. Two constraints shape the approach:

- **This change depends on `add-session-position-ledger` (ships first).** After that
  change, each session's open positions (quantity + weighted-average cost + opened date)
  live in a `session_positions` ledger that is the source of truth for holdings and cost
  basis. Cash is not stored per session (the broker account is account-wide); it is
  derived (see below). The only other per-session anchors in the DB are
  `allocated_capital` (seed) and `total_pnl` (running realized). The broker is used only
  to price positions (live quotes).
- **Schema is owned by Alembic**; models never `create_all` at runtime. This change's
  migration chains after the ledger migration (see Migration Plan). JSONB point-in-time
  payloads already have precedent on `ai_portfolio_events` (`actions_taken`, `research`).

## Goals / Non-Goals

**Goals:**
- A persisted, queryable daily equity curve per active AI session.
- A once-a-day P&L push report with per-session lines + best/worst holding.
- Idempotent capture so re-runs (retries, manual re-trigger) never duplicate a day.

**Non-Goals:**
- Intraday or per-trade valuation history (one snapshot per day only).
- Reconstructing history for days the job did not run (no backfill).
- Exact per-session cash when two sessions hold the same ticker in one broker account
  (see Risks) — out of scope for the paper-trading MVP.
- Generic price-history ingestion / backtesting (explicitly out of project scope).

## Decisions

**Valuation = equity accounting from the ledger, not `account.portfolio_value`.**
`total_value = allocated_capital + realized total_pnl + Σ(market_value − cost_basis)`
over the session's ledger positions (quantity + `avg_cost` from `session_positions`,
`market_value` from `broker.get_quotes`). `positions_value = Σ market_value`;
`cash_value = total_value − positions_value`. Rationale: `account.portfolio_value` is
account-wide and cannot be attributed to one session when the account backs several; the
ledger is per-session by construction, and equity accounting ties to the session's own
seed + realized P&L. Alternative (use account totals directly) rejected — wrong the moment
a second session exists.

**Per-position breakdown stored as a JSONB column, not a child table.** A snapshot is a
denormalized point-in-time record; per-ticker detail (`quantity, price, market_value,
unrealized_pnl, return_pct`) is read back as a unit for the report and possible future
per-holding charts. Follows the `actions_taken`/`research` JSONB precedent and avoids a
second table + migration. Scalar aggregates (`total_value`, `daily_pnl`, …) stay as
columns so the equity curve and P&L are cheap to query/sort.

**Idempotency via `UNIQUE(session_id, snapshot_date)` + read-then-upsert in the
service.** `record_value_snapshot` selects the existing `(session, date)` row and
updates it, else inserts. Rationale: portable, explicit, easy to test; avoids relying
on dialect-specific `ON CONFLICT`. The unique constraint is the backstop.

**Synchronous endpoint, work done inline.** Snapshotting is a few broker reads +
inserts per session — cheap and bounded, unlike agent rebalances. So
`POST /snapshot-daily` computes, records, reports, and returns counts directly (no
thread-pool job runner). Mirrors the "compute inline then `notifier.send`" pattern.

**`snapshot_date` from an injectable `as_of`, defaulting to today in the cron
timezone.** The service takes `as_of: date | None`; the endpoint passes
`datetime.now(America/New_York).date()` so the snapshot date aligns with the market
close and the sidecar TZ. Tests pass an explicit `as_of` for determinism.

**Reuse `REBALANCE_CRON_TOKEN` and the existing `require_valid_cron_token`
dependency.** One shared cron secret for all cron-triggered endpoints; no new setting.
Alternative (a dedicated snapshot token) rejected as needless surface.

**Report:** per-session line `"<strategy>: <total_value> (<±daily_pnl>, <±pct>)"`;
then `"Best: <ticker> <±pct>   Worst: <ticker> <±pct>"` chosen from every held position
across all snapshotted sessions ranked by `return_pct`. If no session has any holdings,
the best/worst line is omitted. Delivered through the existing safe-notify wrapper so a
notifier failure is logged, not raised.

**`daily_pnl_pct = daily_pnl / baseline`** with `baseline > 0` guarded (else `0.0`),
where `baseline` is the prior snapshot's `total_value` or `allocated_capital`.

## Risks / Trade-offs

- **Depends on the position ledger.** Valuation reads `session_positions`; this change
  must be applied after `add-session-position-ledger` and its migration must chain after
  the ledger migration. → Mitigation: dependency is stated in the proposal and the
  migration plan; the snapshot code reads the ledger service, not broker positions.
- **Missed run day.** If the job doesn't run one day, the next `daily_pnl` spans the gap
  (change since the *last* snapshot, not since yesterday). → Accepted and defined that
  way in the spec ("since the prior snapshot"); no backfill.
- **Quote availability at run time.** At 16:15 ET equities have closing prices and crypto
  is live; a missing quote for one ticker must not sink the whole session snapshot. →
  A position whose quote can't be fetched is valued at its last/avg cost and the failure
  logged, mirroring the executor's per-ticker isolation.

## Migration Plan

1. Apply `add-session-position-ledger` first. Then ship this change's additive Alembic
   migration (`down_revision` = the ledger migration head) creating
   `session_value_snapshots`; deploy backend code; then add the `SNAPSHOT_SCHEDULE` cron
   entry. Order is safe because the table exists before the cron can call the endpoint.
2. Rollback: remove the cron entry, then `alembic downgrade` drops the table. No other
   table is touched; existing behavior is unaffected (purely additive).
