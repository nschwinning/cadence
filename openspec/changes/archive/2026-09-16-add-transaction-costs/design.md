## Context

See proposal.md — Why. Relevant current state (from the codebase):

- Every persisted trade flows through one function, `record_trade`
  (`paper_trading/service.py`), which sets `notional = quantity * price`. It is
  the only write path for a `PaperTrade` row, and it is only called for executed
  fills (skipped orders never become trades).
- Session valuation (`compute_session_value`) derives
  `total_value = allocated_capital + total_pnl + unrealized_total`; `cash_value`,
  the daily `SessionValueSnapshot`, and the live `session_kpis` all derive from
  `total_value`. `PaperTradingSession.total_pnl` is cumulative **gross** realised
  P&L, mutated only in `update_session_last_run`.
- Realised P&L per closed position is `(exit − entry) * quantity` in
  `record_closed_position`.
- Rebalance prompts are append-only rows in `rebalance_prompt`; the active prompt
  is `MAX(version)`. New versions are added by an Alembic `op.bulk_insert` (pattern
  in migration `a1d4e7c2b9f8`). Sessions freeze the active version at build
  (`rebalance_prompt_version`), so a new version only affects sessions built after
  it becomes active. Current migration head is `c3f6a9d1e0b4`.
- `settings` (config.py) already carries tunables like `SHARPE_RISK_FREE_RATE`.

## Goals / Non-Goals

**Goals:**

- Charge a fixed, configurable per-trade cost that is impossible to bypass.
- Reflect fees in portfolio value / total return / snapshots while keeping gross
  realised P&L (both session `total_pnl` and per-position) untouched.
- Make fees observable (a KPI field + tile).
- Teach the rebalancer about the cost via a new prompt version.

**Non-Goals:**

- No retroactive re-pricing of historical trades.
- No per-symbol / percentage / tiered fee model — a single flat amount only.
- No change to order routing, sizing, or the AI **build** prompt.
- Not folding fees into `ClosedPosition.realized_pnl`.

## Decisions

**1. Separate `total_fees` accumulator, not folded into `total_pnl`.**
Add a non-nullable `total_fees: float` column (default `0.0`) to
`paper_trading_sessions`. Valuation becomes
`allocated_capital + total_pnl − total_fees + unrealized`. Keeping fees separate
preserves `total_pnl` and per-position realised P&L as clean gross figures and
lets us surface fees as their own KPI. Alternative (subtract from `total_pnl`) was
rejected: it conflates trading P&L with costs and loses fee visibility.

**2. Charge at `record_trade` (single choke point).**
`record_trade` increments the session's `total_fees` by
`settings.TRANSACTION_COST_USD` for each trade it persists. Because every executed
trade — build buys, rebalance buys/sells, closes — routes through here, no caller
can forget to charge, and skipped orders (never recorded) are correctly free.
Alternative (count executed trades at each AI caller and pass a `fees_delta`) was
rejected as more code and easy to miss on a future caller.

**3. Cost is a tunable setting, default `1.0`.**
`TRANSACTION_COST_USD: float = 1.0` in `config.py`, mirroring
`SHARPE_RISK_FREE_RATE`. Lets ops change it without a code edit; tests can
override the setting.

**4. Prompt v2 states the cost statically.**
Seed `rebalance_prompt` version 2 via `op.bulk_insert` in the same migration,
copying v1's instructions/input template verbatim and appending a sentence: each
executed trade (buy or sell) costs ~$1, so avoid churning small positions whose
expected benefit is below the round-trip cost. Static text (not a placeholder) is
enough because the amount is a constant default; this avoids threading a new token
through the agent renderer. The value in the prompt and the `TRANSACTION_COST_USD`
default are kept consistent by convention (both "$1").

**5. Backfill `total_fees = 0.0`, not from trade history.**
Existing sessions' P&L/value was computed fee-free; backfilling from historical
trade counts would retroactively drop their reported values. Fees are
forward-looking, so existing rows start at `0.0`.

## Risks / Trade-offs

- [Prompt value drifts from the setting] The prompt says "$1" statically while
  `TRANSACTION_COST_USD` is tunable → Mitigation: default is `1.0`; if ops changes
  the setting materially, add a follow-up prompt version. Documented as the
  accepted trade-off of the static-text decision.
- [Existing active sessions incur fees under a fee-unaware prompt] Sessions frozen
  on v1 will pay real fees but their agent won't know → this is the intended
  consequence of the per-session freeze design; acceptable and noted in the spec.
- [Fee charged even if a paper order is later cancelled] `record_trade` charges at
  record time; paper trades default to `filled`, so this is effectively a
  non-issue today → Mitigation: revisit if/when non-filled trades are recorded.
- [Test DB rebuild] The new `total_fees` column on an existing table requires
  dropping `cadence_test` so conftest's `create_all` rebuilds it.

## Migration Plan

One new Alembic migration, `down_revision = 'c3f6a9d1e0b4'` (new head):

1. `add_column` `paper_trading_sessions.total_fees` as nullable `Float`.
2. Backfill `UPDATE paper_trading_sessions SET total_fees = 0 WHERE total_fees IS NULL`.
3. `alter_column` `total_fees` to `nullable=False` (server_default `0`/model default).
4. `op.bulk_insert` a `rebalance_prompt` row with `version = 2` and the cost-aware
   instructions + copied input template.

`downgrade` drops the `total_fees` column and deletes the `version = 2`
`rebalance_prompt` row. Rollback is safe: sessions built while v2 was active would
fall back to `MAX(version)=1` resolution only if also un-frozen, which is out of
scope for this rollback window.
