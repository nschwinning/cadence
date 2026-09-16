# Track each session's open positions in a per-session ledger

## Why

A session's open positions exist only in the broker account today, and the account
is shared across all sessions. To attribute holdings to one session the code
intersects `broker.get_positions()` with the portfolio's ticker list
(`portfolio.stocks`) — which is wrong the moment two sessions hold the same ticker
(each claims the account's whole position) and forces cost basis to be read from the
broker and the holding-start date to be reconstructed by scanning `paper_trades`.
This ambiguity blocks a trustworthy per-session equity curve. We want the database
to be the source of truth for what each session holds and at what cost.

## What Changes

- **Add a per-session open-position ledger.** New `session_positions` table with one
  row per `(session_id, ticker)` currently held, carrying `quantity`, weighted-average
  `avg_cost`, and `opened_at`. A unique constraint enforces one open row per session
  per ticker.
- **Make fills maintain the ledger.** The two execution choke points that already see
  every fill — build (`_record_trades`) and rebalance/close (`_apply_rebalance_trades`)
  — update the ledger: a buy opens a new row or increases quantity and re-computes the
  weighted-average cost; a sell reduces quantity and, on a full exit, removes the row.
- **Make the ledger the source of truth for holdings and cost basis.** Rebalance
  computes share deltas against the ledger's quantities (not the broker's account
  positions); close liquidates the ledger's open positions; realized profit and loss
  on exit uses the ledger's `avg_cost` (entry price) and `opened_at` (entry date)
  instead of the broker's `avg_cost` and a `paper_trades` scan. The broker is used only
  to submit orders and to price positions (live quotes) — no longer to answer "what
  does this session hold."
- **Retire the `portfolio.stocks` intersection for holdings.** `portfolio.stocks` stays
  as the AI candidate/target hint, but is no longer intersected with broker positions to
  determine current holdings.

There is currently a single paper portfolio. Rather than backfill approximate cost
basis, the migration path is to **close that portfolio before deploy** (the existing
close flow flattens the broker account) and **build a fresh portfolio afterward**, so
every position opens through the ledger-aware code with exact cost basis. No data
backfill is needed, so this change adds none.

## Capabilities

### New Capabilities
<!-- none: this extends the existing ai-paper-trading capability -->

### Modified Capabilities
- `ai-paper-trading`: ADD a requirement to maintain a per-session open-position ledger
  as the source of truth for holdings and cost basis; MODIFY "Record sessions, trades,
  runs, and closed positions" so fills update the ledger and realized P&L is derived
  from it.

## Impact

- Affected specs: `ai-paper-trading` — ADDED "Maintain a per-session open-position
  ledger", MODIFIED "Record sessions, trades, runs, and closed positions".
- Affected code (backend, schema): Alembic migration (`down_revision = e1f4c2a7b9d5`)
  creating `session_positions` (UUID PK, `session_id` FK `ON DELETE CASCADE`, `ticker`,
  `quantity`, `avg_cost`, `opened_at`, `updated_at`) with `UNIQUE(session_id, ticker)`;
  matching ORM model in `paper_trading/models.py`.
- Affected code (backend, behavior): `paper_trading/service.py` (ledger upsert on buy
  with weighted-average cost, reduce/close on sell, `get_open_positions`/`list` reads;
  realized-P&L helper reads ledger `avg_cost`/`opened_at`); `ai_portfolio/service.py`
  (`_record_trades` and `_apply_rebalance_trades` update the ledger; rebalance reads the
  ledger for current holdings and passes ledger quantities to the executor's delta math;
  `close_session` reads the ledger for what to liquidate; drop the
  `broker.get_positions()` ∩ `portfolio.stocks` intersection and the `paper_trades`
  entry-date scan); `ai_portfolio/executor.py` (rebalance/close operate on ledger
  quantities rather than broker `Position.quantity`, still pricing via broker quotes).
- Migration path (ops): with a single existing paper portfolio, close it before deploy
  and build a fresh one afterward (see above) — no data migration or backfill code.
- Tests: ledger upsert/weighted-average-cost and reduce/close unit tests; build opens
  ledger rows; rebalance deltas computed against the ledger (including when another
  session holds the same ticker — no cross-contamination); close liquidates ledger
  positions; realized P&L uses ledger basis + open date.
- Backwards compatibility: additive table. Behavior changes how holdings are sourced; the
  close-and-rebuild migration path avoids any stale-holdings inconsistency. Downstream,
  this unblocks `add-session-value-snapshots` to value sessions from the ledger instead of
  the intersection.
