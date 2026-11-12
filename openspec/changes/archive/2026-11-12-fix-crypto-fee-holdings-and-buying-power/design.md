## Context

- Alpaca deducts its crypto buy fee from the coin received (market orders pay the taker rate,
  0.25% at the base tier — `settings.CRYPTO_FEE_PCT`). `paper_trading.service.book_fill` books the
  full filled quantity into `SessionPosition` and also adds the fee to `total_fees`, so ledgers sit
  ~0.25% above the account per crypto buy and the fee is counted twice in the session's cash
  identity (`cash = allocated + pnl − fees − Σ qty × avg_cost`).
- Full crypto exits sell the ledger quantity → more than held → refused by the long-only guard.
- Alpaca rejects crypto orders below $10 notional; `MIN_CRYPTO_NOTIONAL_USD` is 1.0.
- Admin orders explicitly rejected stay `submitted` until "Reconcile now".
- `AccountInfo.buying_power` is Alpaca's `buying_power` (margin, up to 4× intraday); Alpaca also
  reports `non_marginable_buying_power` (cash-only, the crypto limit).

## Goals / Non-Goals

**Goals:** ledgers that match the account for crypto; exits that always go through; no sub-$10
crypto orders; a one-time repair for existing gaps; correct buying-power ceiling.

**Non-Goals:** reading the exact per-order fee from account activities (rate-based estimate plus
the 1% write-off tolerance covers tier differences); changing equity booking; bots (equity-only).

## Decisions

1. **Net booking in `book_fill`**: for `AssetClass.CRYPTO` buys the ledger quantity is
   `filled × (1 − CRYPTO_FEE_PCT)` at the filled price; the `PaperTrade` keeps the filled quantity
   and its fee; `total_fees` still gets the fee. Cash identity: `alloc − fee − net × price =
   alloc − gross` — correct, fee counted once.
2. **Crypto sell cap**: `AIPortfolioExecutor` caps every crypto sell quantity at
   `OrderGateway.held_quantity(ticker)` before submitting. When booking a crypto sell, a ledger
   remainder of at most 1% of the pre-sell quantity is closed as dust (the position is fully
   exited), so a capped full exit leaves no phantom remainder.
3. **Minimum**: `MIN_CRYPTO_NOTIONAL_USD = 10.0` (executor skips below it, existing reason path).
   Admin `_adjust` estimates notional from the broker position's `current_price` (or
   `market_value / quantity`, else a quote) and skips crypto below $10 with `below_minimum`.
4. **Write-off** (`admin.service.write_off_positions`): eligible = crypto, status `shortfall`,
   broker quantity > 0, gap ≤ 1% of Cadence quantity, no pending order. Recomputed at execution;
   the gap is split over the `SessionPosition` rows of that coin proportionally to quantity
   (rounded to 9 dp, the last row takes the remainder), `avg_cost` unchanged, committed in one
   unit. Eligible rows are not offered Restore. `PositionRow` gains `write_off_eligible` and
   `write_off_quantity`; endpoint `POST /admin/write-off-positions {symbol|null}` (extra=forbid);
   outcomes reuse the flatten/restore shape with result `written_off`.
5. **Admin rejections**: `OrderGateway` records an `OrderError` for an `ADMIN` owner as closed
   (`state = resolved`, not booked) via `journal.record_submitted(..., close=True)`.
6. **Buying power**: `AccountInfo.cash_buying_power: float | None` from
   `non_marginable_buying_power`; `AccountFigures`/schema/TS gain `cash_buying_power`; the tile
   uses `min(buying_power, cash_buying_power ?? buying_power)`; the Admin page labels both.

## Risks / Trade-offs

- The fee rate is configured, not read per order: a different Alpaca tier leaves a small residue,
  which the 1% write-off absorbs.
- Dust-closing on sells could close a deliberately tiny remainder (<1% of the position); such a
  remainder would be below the $10 minimum to trade anyway.
- Write-off changes ledgers without an order; it is confirmed, bounded to 1%, crypto-only.

## Migration Plan

No schema change. After deploy: Admin → Write off all (repairs existing crypto gaps), Reconcile now
(clears lingering admin rejections). Rollback: revert code (written-off quantities stay lowered,
which matches the account).

## Open Questions

None.
