## 1. Schema: session_positions table

- [x] 1.1 Add a `SessionPosition` ORM model to `paper_trading/models.py` (UUID PK, `session_id` FK → `paper_trading_sessions.id` `ON DELETE CASCADE`, `ticker` Text, `quantity` Float, `avg_cost` Float, `opened_at` timestamp, `updated_at` timestamp) with `UniqueConstraint(session_id, ticker)` and an index on `session_id`. Verify the table appears in `Base.metadata`.
- [x] 1.2 Add an Alembic migration (`down_revision = "e1f4c2a7b9d5"`) creating the table + unique constraint; `downgrade` drops it. Verify `uv run alembic upgrade head` → `downgrade base` → `upgrade head` and `uv run alembic check` is clean.

## 2. Backend: ledger service operations

- [x] 2.1 In `paper_trading/service.py` add `apply_fill_to_ledger(session, *, session_id, ticker, side, shares, price)`: a buy opens a new entry or increases quantity and re-computes weighted-average cost (`(q*avg + s*price)/(q+s)`); a sell reduces quantity and deletes the entry when `abs(quantity) <= epsilon`. Verify with unit tests: open, average-up over two buys, partial sell, and full exit removes the row.
- [x] 2.2 Add reads `get_open_position(session, session_id, ticker)` and `list_open_positions(session, session_id)`. Verify a service test returns only nonzero entries for the right session.
- [x] 2.3 Add a helper returning a position's entry basis `(avg_cost, opened_at)` for realized-P&L, read before a sell decrements it. Verify with a test that the basis reflects the pre-sell weighted-average cost and original opened date.

## 3. Backend: wire the ledger into build / rebalance / close

- [x] 3.1 `ai_portfolio/service.py` `_record_trades` (build): call `apply_fill_to_ledger` for each executed buy. Verify a build test creates one ledger row per bought ticker with the expected quantity/avg cost.
- [x] 3.2 `_apply_rebalance_trades` (rebalance + close): call `apply_fill_to_ledger` for each executed fill; for sells, read the ledger basis first and pass `entry_price=ledger.avg_cost` / `entry_date=ledger.opened_at` into `record_closed_position` (remove the `paper_trades` first-`_long` scan and the `pos.avg_cost` read). Verify realized P&L uses the ledger basis in a rebalance and a close test.
- [x] 3.3 Rebalance: build current holdings from `list_open_positions` (ledger quantities) instead of `broker.get_positions()` ∩ `portfolio.stocks`; still fetch `current_price` from broker quotes. Adjust `executor.execute_rebalance` to take ledger-sourced current quantities for its delta math. Verify a rebalance test where another session holds the same ticker computes deltas from only this session's ledger (no cross-contamination).
- [x] 3.4 Close: read the ledger for `(ticker, quantity)` to liquidate instead of the broker intersection; adjust `executor.execute_close` accordingly. Verify a close test liquidates exactly the ledger's open positions and empties the ledger.
- [x] 3.5 Remove the now-unused `broker.get_positions()` holdings intersection and `_build_holdings`-via-`portfolio.stocks` quantity path (keep `portfolio.stocks` as the AI candidate/target hint). Verify the full backend suite still passes.

## 4. Verification

- [x] 4.1 Backend: `uv run ruff check .`, `uv run mypy src/cadence`, `uv run pytest` all pass; Alembic round-trip + `alembic check` clean.
- [x] 4.2 `openspec validate add-session-position-ledger --strict` passes.
- [x] 4.3 Confirm no remaining `broker.get_positions()`-as-holdings-source reads (grep) and that rebalance/close/realized-P&L all read the ledger.
