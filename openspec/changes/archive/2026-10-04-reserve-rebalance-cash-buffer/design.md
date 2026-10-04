## Context

`AIPortfolioExecutor` sizes positions off a single scalar base:

- **Build** (`execute_build` → `_open_long`): base = `self.allocated_capital`.
- **Rebalance** (`execute_rebalance`): base = `base_capital` (the session's live
  marked-to-market value, passed by `run_rebalance_event` as
  `valuation.total_value`, or the crypto budget for a crypto-only run).

Per ticker the target market value is `base × weight`, and the weights sum to
~1.0 after normalization and guardrail clamping. So a fully-invested target
plans net buys ≈ (current cash), and the `$1`/trade `TRANSACTION_COST_USD`
(charged on top at `record_trade`) plus live-Alpaca fill slippage push
unallocated cash below zero. The fix reserves a cash buffer by shrinking that
base **once, before** the per-ticker sizing loop, so nothing downstream changes.

## Goals / Non-Goals

**Goals**
- Unallocated cash stays ≥ 0 after a fully-invested build or rebalance under the
  immediate-fill stub, and is robust to fees + modest slippage on live Alpaca.
- Reserve = `max(pct × base, estimated_fees)`, applied at build and rebalance
  (including crypto-only), with no new persisted state and no migration.
- Preserve the delta model, guardrail clamp, crypto-only scoping, market_open
  equity-skip, and sells-before-buys phasing exactly.

**Non-Goals**
- Not reserving against worst-case slippage precisely (a small % buffer absorbs
  it; we do not model per-order slippage).
- No new DB column, no per-session override of the buffer (global setting only).
- Not changing how fees are charged or accumulated (`record_trade` unchanged).

## Decisions

### D1 — Buffer formula: `max(pct, fee estimate)`
`reserve = max(base × REBALANCE_CASH_BUFFER_PCT, estimated_fee_total)` and the
sizing base becomes `net_base = max(base − reserve, 0.0)`.

- `REBALANCE_CASH_BUFFER_PCT` is a new float setting, default `0.015` (1.5%).
- `estimated_fee_total = candidate_order_count × settings.TRANSACTION_COST_USD`.

### D2 — Candidate order count = union-of-tickers upper bound
Fees are charged per executed trade, but the executed count isn't known until
after sizing (chicken-and-egg). We use a deterministic **upper bound**: the
number of candidate tickers for the run — `len(set(current_positions) |
set(target_weight))` at rebalance, `len(stocks)` at build. At most one order is
placed per ticker, so this never under-reserves. Over-reserving (a ticker that
ends up a no-op) only leaves marginally more cash, which is safe and desirable.
This avoids a two-pass sizing loop.

### D3 — Apply once, at the base, before the loop
At rebalance, compute `net_base` from `base` immediately after guardrail
clamping and before the Phase-0 sizing loop; pass `net_base` into
`_plan_equity`/`_plan_crypto` in place of `base`. At build, compute `net_base`
from `allocated_capital` once and size each `_open_long` against
`net_base × weight` (mirrors the existing `allocated_capital × weight`). The
crypto-only path already sets `base` to the crypto budget before this point, so
the same reduction applies to it without special-casing.

### D4 — Shared helper for the reserve
A small pure helper (e.g. `_reserve_cash_buffer(base, candidate_count)`
returning `net_base`) keeps build and rebalance consistent and unit-testable in
isolation. It reads `settings.REBALANCE_CASH_BUFFER_PCT` and
`settings.TRANSACTION_COST_USD`.

### D5 — Disabled when both inputs are zero
With `REBALANCE_CASH_BUFFER_PCT == 0` and `TRANSACTION_COST_USD == 0`,
`reserve == 0` and `net_base == base`, so existing tests that assume full
deployment with no cost keep passing unless they opt into a non-zero buffer.

## Risks / Trade-offs

- **Existing tests assume full deployment.** The default 1.5% buffer changes
  build/rebalance quantities in tests that assert exact shares. Mitigation:
  audit `test_ai_portfolio_executor.py` (and any build/rebalance qty assertions)
  and update expectations, or set the buffer to 0 in fixtures that assert
  no-buffer behavior. Document in tasks.
- **Over-reserving on large portfolios** when the fee estimate dominates (many
  tickers × $1). Acceptable: it only leaves more idle cash, never negative, and
  the percentage path dominates for normal capital sizes.
- **Not a hard guarantee against large slippage.** A 1.5% default comfortably
  covers typical fills; extreme gaps could still overspend. Out of scope to
  model precisely; the setting is tunable.

## Migration Plan

None — settings + executor logic only. New setting has a safe default; existing
sessions and data are unaffected. No DB/schema/migration.

## Open Questions

- Default percentage: `0.015` proposed; tunable via `REBALANCE_CASH_BUFFER_PCT`.
