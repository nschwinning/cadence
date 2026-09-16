## Context

See proposal.md — Why. Current state, from tracing the code:

- **No open-positions table exists.** The paper_trading domain has `paper_trading_sessions`,
  `paper_trades` (individual fills), `session_runs` (audit), and `closed_positions`
  (exit-only). A session's *open* state is derived at runtime from
  `broker.get_positions()` (account-wide) intersected with `portfolio.stocks`.
- **`portfolio.stocks`** is a `ARRAY(Text)` of tickers on the portfolio — no quantities,
  no cost. Rewritten wholesale by rebalance from the AI's targets.
- **Cost basis is broker-derived.** Rebalance/close read `Position.avg_cost` (Alpaca
  `avg_entry_price`; the stub keeps a running weighted average per fill). `entry_date` for
  realized P&L is reconstructed by scanning `paper_trades` for the first `_long` trade.
- **Two write choke points already see every fill** with `ticker, side, shares, price,
  filled_price`: `_record_trades` (build) and `_apply_rebalance_trades` (rebalance + close).
  Both are the natural place to update a ledger.
- Fills report the price paid via `Order.filled_price`, with the pre-trade quote as a
  documented fallback when Alpaca hasn't filled yet (`filled_price or price`).

## Goals / Non-Goals

**Goals:**
- One authoritative DB record of each session's open positions (quantity + weighted-avg
  cost + opened date), attributed per session.
- Remove the `broker.get_positions()` ∩ `portfolio.stocks` intersection as the holdings
  source for rebalance, close, and (downstream) valuation.
- Preserve realized-P&L semantics while sourcing entry price/date from the ledger.

**Non-Goals:**
- Continuous reconciliation of the ledger against the live brokerage (no drift detector;
  the ledger is authoritative for paper trading). Corporate actions / manual broker
  changes are out of scope.
- Exposing open positions via a read API / UI panel (nice follow-up; not required to
  remove the ambiguity).
- Changing order sizing, pricing, or the agent seam.

## Decisions

**One row per `(session_id, ticker)`, `UNIQUE(session_id, ticker)`.** The ledger holds
only *open* positions; a full exit deletes the row (mirrors how the runtime picture works
today, and keeps "held tickers" = "rows"). Columns: `quantity`, `avg_cost`, `opened_at`,
`updated_at`. Rationale: simplest source of truth; a deleted-on-exit row means a re-buy
starts a fresh basis, matching the stub broker's current `avg_cost` reset on full exit.

**Weighted-average cost on buys, in the DB.** On a buy fill:
`avg_cost = (qty*avg_cost + fill_qty*fill_price) / (qty+fill_qty)`, `quantity += fill_qty`.
On a sell: `quantity -= fill_qty`; delete when `quantity <= ~0` (epsilon for float/crypto).
This ports the stub broker's `_apply_to_position` math (the current de-facto behavior) into
per-session DB state. Cost basis uses `filled_price or price` — the same value already
recorded on `paper_trades`, so the ledger and trade rows agree.

**Update the ledger at the existing choke points.** `_record_trades` (build) and
`_apply_rebalance_trades` (rebalance + close) call a new
`paper_service.apply_fill_to_ledger(session, session_id, ticker, side, shares, price)` per
executed `TradeResult`. No new call site is introduced; both already iterate executed
fills. Realized P&L on a sell reads the ledger entry *before* decrementing it, so
`entry_price = ledger.avg_cost` and `entry_date = ledger.opened_at` — replacing
`pos.avg_cost` and the `paper_trades` first-`_long` scan.

**Ledger is the holdings source; broker is orders + prices.** Rebalance builds its
"current holdings" dict from `list_open_positions(session_id)` (quantity from the ledger)
and still fetches `current_price` from broker quotes for the delta math and agent context.
Close reads the ledger for `(ticker, quantity)` to liquidate. `execute_rebalance` /
`execute_close` are adjusted to take ledger-sourced quantities rather than
`Position.quantity`. `broker.get_positions()` is no longer consulted for holdings.

**No data backfill — close and rebuild instead.** There is a single existing paper
portfolio. Rather than seed approximate cost basis into the ledger, the operator closes
that portfolio before deploy (the existing close flow flattens the broker account) and
builds a fresh one afterward, so every position opens through the ledger-aware code with
exact basis. This avoids backfill code entirely and sidesteps the accuracy caveat of
seeding from the broker's blended average. (If more portfolios existed and liquidation
were undesirable, a one-time idempotent seed from `broker.get_positions()` ∩
`portfolio.stocks` would be the alternative — not built here.)

## Risks / Trade-offs

- **Ledger vs. broker drift.** After deploy the ledger, not the broker, defines holdings;
  if the broker account diverges (manual trades, corporate actions), paper results follow
  the ledger. → Accepted: for paper trading the ledger is authoritative by design; a
  reconcile tool is a possible future change, noted as a Non-Goal.
- **Stale holdings if not migrated.** If the existing portfolio is neither closed before
  deploy nor otherwise seeded, its ledger is empty and the next rebalance would double-buy
  on top of the broker positions it can't see. → Mitigation: the close-and-rebuild
  migration path (below) is mandatory, not optional; call it out in the deploy runbook.
- **Float precision on full exit.** Crypto fractional quantities may not net to exactly 0.
  → Delete the row when `abs(quantity) <= a small epsilon` (reuse the crypto precision
  already used in the executor).
- **Ordering with the snapshots change.** `add-session-value-snapshots` must be rebased to
  value sessions from the ledger and to chain its migration after this one. → Called out
  explicitly; this change ships first.

## Migration Plan

1. **Close the existing portfolio first** (via the current close flow) so the broker
   account is flat — do this before the ledger code deploys.
2. Ship the additive Alembic migration (`down_revision = e1f4c2a7b9d5`) creating
   `session_positions`; deploy backend code (fills now maintain the ledger; rebalance/close
   read it).
3. **Build a fresh portfolio** — its positions open through the ledger-aware code with
   exact cost basis. The ledger and the broker account start consistent.
4. Rollback: revert code (fills stop writing the ledger; rebalance/close revert to the
   broker intersection), then `alembic downgrade` drops the table. No other table changes.
