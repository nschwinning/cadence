## Why

The AI returns target weights, but the executor sizes equities in whole shares
(`float(int(capital / price))`), so every equity position rounds *down* to a whole
share and the sub-one-share remainder is left as idle cash. On a portfolio of many
names this strands a meaningful slice of capital and makes positions drift below
their intended target weights. Alpaca already supports fractional equity trading for
assets flagged `fractionable`, and the entire stack below the executor (order model,
`PaperTrade` columns, Alpaca/stub submit paths) is already float-capable — only the
executor's sizing math truncates. Enabling fractional equity sizing lets each position
hit its target weight precisely and puts the stranded remainder to work.

## What Changes

- Size fractionable equities in **fractional** share quantities (rounded to a new
  `EQUITY_QTY_PRECISION`) at build, rebalance, and exit, instead of truncating to
  whole shares. Non-fractionable equities keep today's whole-share behavior.
- Gate the behavior on the asset's fractionability: persist a nullable `fractionable`
  flag on the `assets` row, populated at add-time from `broker.get_asset(...)`, with an
  Alembic migration that adds the column and backfills existing rows from Alpaca. An
  unknown/NULL flag is treated as **non-fractionable** (whole shares) — a safe default.
- Replace the equity "skip allocations worth less than one share" rule with a
  **dollar dust threshold** (`MIN_EQUITY_NOTIONAL_USD`), analogous to crypto's
  `MIN_CRYPTO_NOTIONAL_USD`, so tiny allocations are skipped by dollar value rather than
  by being under one share. The rebalance `|delta| < 1 share` no-op guards become a
  minimum-notional / precision-epsilon guard for fractionable names.
- Verify (and if necessary fix) that the equity orders the executor submits to Alpaca
  satisfy Alpaca's fractional constraints: fractional equity orders must be **market or
  day-limit orders with `time_in_force=day`**. Non-fractional (whole-share) orders are
  unaffected.
- No change to the AI output schema — the AI still returns `allocation_pct` weights;
  this is purely how the executor turns a weight + capital into a share quantity.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ai-paper-trading`: Order sizing — fractionable equities are sized in fractional
  shares to hit target weights precisely; a dollar dust threshold replaces the
  whole-share skip; fractionability is sourced from a persisted per-asset flag.

## Impact

- **Backend / executor**: `ai_portfolio/executor.py` equity sizing at `_open_long`
  (build buy), `_plan_equity` (rebalance delta), and the equity close/exit path; new
  constants `EQUITY_QTY_PRECISION` and `MIN_EQUITY_NOTIONAL_USD`.
- **Assets**: `assets/models.py` gains a nullable `fractionable` column; `assets/service.py`
  `add_asset` stores `broker.get_asset(...).fractionable`; new Alembic migration adds the
  column + backfills existing rows from Alpaca (fail-open to NULL).
- **Broker/order path**: verify equity order type/TIF submitted to Alpaca is
  fractional-compatible (`broker/alpaca.py` submit path); adjust only if it is not.
- **No change** to the AI agent output schema, the `PaperTrade`/`Order` models
  (already float), or the frontend.
- **Verification gate**: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`,
  plus migration round-trip (`alembic upgrade head` / `downgrade`, `alembic check`).
