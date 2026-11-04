## Context

See proposal.md — Why. Two seams are relevant:

- **Trade ledger.** `BotTrade` rows record each fill (`side`, `ticker`, `quantity`, `filled_price`, `fees`, `created_at`) but do **not** store per-trade or round-trip realized P&L. Exits fold realized P&L only into the session's running `BotSession.realised_pnl` total (`engine.py` `exit()`: `bot.realised_pnl += (filled_price - position.avg_price) * filled_qty`). The `ticker` stored on a trade is the broker (`alpaca_symbol`) form, consistent between a position's buy and its sell.
- **Position invariants.** A session holds at most one open position per symbol (`uq_bot_positions_session_asset`), `enter()` opens a fresh position (never averages into an existing one), and `exit()` always sells the *entire* position. So, per ticker, recorded fills strictly alternate buy → sell → buy → sell, and each sell closes exactly the position opened by the immediately preceding buy of that ticker.
- **KPIs** are assembled by `bot_session_kpis` into the `BotKpis` dataclass → `BotKpisRead` schema, consumed by `BotSessionPage.tsx`. Open positions are already embedded in the `/sessions/{id}` payload, ordered by ticker via the `positions` relationship `order_by`.

## Goals / Non-Goals

**Goals:**
- Report the best and worst *closed round-trip* realized P&L (with ticker) in the per-session KPIs, computed on read from the existing ledger.
- Let the detail view re-sort open positions by ticker (default) or opened timestamp.

**Non-Goals:**
- No per-trade P&L column, migration, or backfill on `BotTrade`.
- No change to exit/tick/snapshot logic, the trade ledger shape, the list endpoint, or the positions `order_by` default.
- No ranking of still-open positions by unrealized P&L (best/worst is realized, closed round-trips only).

## Decisions

**1. Compute best/worst round-trip on read, not persist it.**
A helper (e.g. `bot_trade_extremes(bot)`) walks the session's trades in chronological order, keeping a per-ticker open-entry basis (price, quantity, entry fees); each sell pops that ticker's basis and yields a closed round-trip P&L of `(sell_price - entry_price) * qty - entry_fees - sell_fees`. It returns the max- and min-P&L round-trips (each as ticker + realized P&L), or `None`/`None` when there are no closed round-trips. The one-position-per-symbol + full-exit invariants make this pairing exact and deterministic, so no stored P&L is needed.
- *Why over a persisted column:* persisting realized P&L on the sell `BotTrade` would need a migration **and** a backfill (by this same reconstruction) to cover existing sessions — strictly more work for an identical result. Reconstruction naturally covers all history. Trade counts per session are small (minutes-cadence bots), so the O(n) walk is cheap and runs only on the KPI read.

**2. Carry best/worst as two optional structured fields on `BotKpis`/`BotKpisRead`.**
Add `best_trade` and `worst_trade`, each an optional object with `ticker` and `realised_pnl` (nullable when no closed round-trip exists). A small nested shape reads better than four flat columns and matches how the frontend renders one tile per figure.
- *Why over a separate endpoint:* the detail page already fetches `/kpis`; folding these in avoids a second round-trip and keeps "performance figures" in one place.

**3. Open-positions sort is frontend-only.**
Positions are already in the loaded session object. A local sort toggle (`ticker` | `opened_at`) re-sorts the in-memory array; ticker remains the default so current behavior is unchanged. No API or `order_by` change — the backend default stays ticker so a fresh load is deterministic.

## Risks / Trade-offs

- [Reconstruction depends on the one-position-per-symbol + full-exit invariants] → Those invariants are enforced today (unique constraint; `exit()` sells the whole position; `enter()` never averages). If a future change introduces partial exits or position averaging, the pairing logic must be revisited — the design note and unit tests make that dependency explicit. Mitigation: unit-test the alternating buy/sell pairing, the no-closed-trade case, and a multi-ticker mix.
- [Fees] → Fees are currently always 0 on paper, but the P&L formula subtracts entry+exit fees so it stays correct if a fee model is introduced later.
- [Best == worst with a single round-trip] → Intentional: with one closed trade it is both best and worst; the tile shows the same figure for each, which is accurate.
