## Context

See proposal.md — Why. All raw material for a day's learning record already exists
but is scattered across three unjoined places (paths under `backend/src/cadence/`):

- **`AIPortfolioEvent`** (`ai_portfolio/models.py:51-114`) — the per-run record.
  Columns include `session_id` (nullable FK → `paper_trading_sessions`, SET NULL),
  `portfolio_id` (nullable FK → `portfolios`, SET NULL), `event_type`
  (`build`/`rebalance`/`close`), `status`, `request_payload`, `result_payload`
  (= the AI reasoning / target allocations / thesis / confidence / portfolio health;
  there is no separate `reasoning` column), `actions_taken` (UI-facing per-ticker
  `TradeResult`s — **drops** filled price), `research`, `trend_context` (the per-run
  technical-indicator **values** handed to the agent for candidates/holdings/dropped
  candidates incl. reversal flags; null when no gating), `run_stats` (machine-readable
  learning blob; null on pre-execution failures), `error`, `duration_ms`, timestamps.
- **`SessionValueSnapshot`** (`paper_trading/models.py:476-527`) — the per-day P&L
  record. Unique `(session_id, snapshot_date)`; fields `total_value`, `cash_value`,
  `positions_value`, `daily_pnl`, `daily_pnl_pct`, `positions` (per-holding JSONB),
  `created_at`. Not linked to an `AIPortfolioEvent`.
- **`PaperTrade`** (`paper_trading/models.py:271-321`) — the trade ledger.
  `ai_portfolio_event_id` (nullable FK, SET NULL) links a trade to its producing run;
  `order_status` (default `FILLED`), `filled_price`/`filled_at` (nullable). Filled price
  is reliably known only **after** `reconcile_session_orders`
  (`paper_trading/service.py:977-1026+`).

`run_stats` (built by `_build_run_stats`, `ai_portfolio/service.py:2404-2444`) already
carries `orders` (executed/skipped/total/all_executed), `trades`
(`TradeResult.to_stats_dict()`, `executor.py:231-237` = `{ticker, side, shares, price,
executed, reason, order_id, order_status, filled_price}`), optional `realized_pnl`,
`account` (`portfolio_value`/`cash_available`/`total_unrealized_pnl`), `gate` (counts),
and `guardrails`. It is deliberately excluded from `AIPortfolioEventRead`
(`api/schemas.py:886-906`); `trend_context` is exposed.

The daily P&L run is a separate cron — `snapshot_all_sessions`
(`ai_portfolio/service.py:1322`) → `record_value_snapshot`
(`paper_trading/service.py:1306-1358`), behind the cron-guarded `/ai-portfolio/snapshot-daily`
endpoint. The rebalance run (`run_rebalance_event`, `service.py:693`) persists the
event + `PaperTrade`s + a `SessionRun` audit row but writes no value snapshot.

## Goals / Non-Goals

**Goals:**

- One consolidated, backend-only row per session per calendar day that joins the
  rebalance decision, the indicator values it saw, the reconciled filled orders, the
  run outcome stats, and that day's P&L — the exact shape offline learning needs.
- Pure **consolidation** of already-persisted data; no recomputation of indicators,
  no re-running of the agent, no change to the rebalance run or the existing snapshot
  job.
- A dedicated cron-guarded assembly job sequenced after the P&L job, idempotent per
  session/day, best-effort per session.

**Non-Goals:**

- No read schema, read API, or frontend surface (mirrors the `run_stats` decision).
- No change to `run_stats`, `trend_context`, `result_payload`, the rebalance run, the
  reconciliation job, or the value-snapshot job.
- No cross-day analytics, aggregation, or export format — a later concern. This change
  only persists the per-day row.

## Decisions

### Table shape: mostly-JSONB document with a few indexed scalar columns

New table `session_daily_run_snapshots`:

- `id` (PK), `session_id` (FK → `paper_trading_sessions`, SET NULL, indexed),
  `portfolio_id` (nullable FK → `portfolios`, SET NULL, indexed — enables per-portfolio
  grouping even if a session row is later detached), `run_date` (`Date`, indexed),
  `created_at`, `updated_at`.
- A **unique constraint on `(session_id, run_date)`** — the idempotency key, mirroring
  `SessionValueSnapshot`'s unique `(session_id, snapshot_date)`.
- `ai_portfolio_event_id` (nullable FK → `ai_portfolio_events`, SET NULL) — the day's
  rebalance run, null when there was none.
- A single JSONB `document` column holding the consolidated payload:
  `{ "run": {event_type, status, result_payload, trend_context, run_stats, duration_ms,
  error} | null, "orders": [ {ticker, side, quantity, price, notional, order_id,
  order_status, filled_price, filled_at, executed_at} ... ], "valuation": {total_value,
  cash_value, positions_value, daily_pnl, daily_pnl_pct, positions} }`.

**Why mostly-JSONB:** the source material (`result_payload`, `trend_context`,
`run_stats`, `positions`) is already schemaless JSONB; promoting every field to a
column would duplicate that shape and churn on every prompt/indicator change. The few
scalars that queries/exports filter on (`session_id`, `portfolio_id`, `run_date`) are
indexed columns; everything else is the document. Alternative considered — fully
denormalized columns — rejected as high-churn for no query benefit given there is no
read API.

### Orders come from the reconciled `PaperTrade` ledger, not `run_stats.trades`

The day's filled orders are read from `PaperTrade` rows for the session dated to
`run_date`, because reconciliation writes authoritative `filled_price`/`filled_at`/
`order_status` onto `PaperTrade` (that is the whole reason the job runs **after** the
P&L/reconciliation step). `run_stats.trades` is still captured inside `run.run_stats`
as the as-decided view, but the top-level `orders` array is the reconciled truth.

### Day selection reuses the P&L job's semantics

Assembly iterates the same sessions the value-snapshot job selects for the day (active
AI-managed sessions; on weekends only crypto-scoped sessions — the weekend gating
already governs which sessions were snapshotted). A session is assembled only if it has
a `SessionValueSnapshot` for `run_date`; a session with no snapshot that day is skipped.
This keeps the learning table aligned 1:1 with the P&L table.

### A day with a value snapshot but no rebalance run still records a row

Weekends, skipped runs, and stocks-only non-trading days produce a value snapshot but
no `AIPortfolioEvent`. The P&L is still worth learning from, so the row is recorded with
`ai_portfolio_event_id = null` and `document.run = null` / `document.orders = []`.
Rationale: the learning table should mirror the P&L table's day coverage; a null run is
information (the day had no decision), not an error. Alternative — skip these days —
rejected because it would silently drop every weekend crypto day from the learning set.

### Finding the day's rebalance event

For a session on `run_date`, select the most recent `AIPortfolioEvent` with
`event_type = rebalance` (or build/close) whose `created_at` falls on that calendar day
in the snapshot timezone. If none, the run portion is null. This matches how
`SessionRun`/`PaperTrade` already associate to a run via `ai_portfolio_event_id`.

### New service fn + cron-guarded endpoint

- Service: `assemble_daily_run_snapshots(session, ...)` in `ai_portfolio/service.py`,
  alongside `snapshot_all_sessions`; iterates selected sessions, upserts one row each,
  best-effort per session (one failure logged and skipped, batch continues).
- Endpoint: a cron-token-guarded `POST` under `/api/v1/ai-portfolio/...` (e.g.
  `/ai-portfolio/daily-run-snapshot`), rejecting missing/invalid token, mirroring
  `/ai-portfolio/snapshot-daily`.
- Deployment adds one cron entry ordered after the `snapshot-daily` cron (scheduling
  concern, not enforced by the endpoint).

## Risks / Trade-offs

- **Reconciliation not yet complete when assembly runs** → filled prices would be stale.
  Mitigation: sequence the cron strictly after the P&L/reconciliation job; the reconciled
  values are read from `PaperTrade` at assembly time, so a later reconciliation is picked
  up on the next (idempotent) run for that day if re-triggered.
- **Timezone mismatch between `run_date` and `AIPortfolioEvent.created_at`** → a run near
  midnight could be attributed to the wrong day. Mitigation: use the same timezone the
  snapshot job uses to derive the calendar day, so the learning row and the value snapshot
  agree on the day boundary.
- **JSONB document drift** → consumers must tolerate schema evolution. Acceptable: this is
  backend-only learning data with no read-API contract; the shape can evolve freely.
- **Unbounded growth** → one row per session per day. Acceptable at current scale; pruning
  is a later concern.

## Migration Plan

- New Alembic migration creating `session_daily_run_snapshots` with the unique
  `(session_id, run_date)` constraint and the indexed scalar columns. `down_revision` =
  the current live head (verify with `uv run alembic heads` at implementation time; the
  most recent head recorded is `c7d8e9f0a1b2` — confirm before writing).
- `upgrade` creates the table + indexes + unique constraint + FKs (all SET NULL / nullable
  so existing rows and future deletes stay valid); `downgrade` drops the table. Single
  linear head preserved.
- Round-trip verified: `uv run alembic upgrade head`, `downgrade`, and `uv run alembic
  check` (no drift).
- Rollback: drop the table (downgrade); no other table or job is touched, so the rest of
  the system is unaffected.
