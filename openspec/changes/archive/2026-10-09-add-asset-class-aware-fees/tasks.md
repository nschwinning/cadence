## 1. Settings

- [x] 1.1 In `config.py` add `CRYPTO_FEE_PCT: float = 0.0025` (documented as the crypto taker fee fraction on notional) and remove `TRANSACTION_COST_USD`; grep the whole repo (`src`, `tests`, any `.env*`/deploy docs) for `TRANSACTION_COST_USD` and confirm every reference is migrated (no stray reads remain).

## 2. Fee charge at the recording choke point

- [x] 2.1 In `paper_trading/service.py` `record_trade`, add a keyword-only `asset_class: AssetClass` parameter and replace the flat `total_fees += TRANSACTION_COST_USD` with `fee = CRYPTO_FEE_PCT * quantity * (filled_price if filled_price is not None else price)` when `asset_class is CRYPTO` else `0.0`, accumulated into `total_fees`; update the docstring. Verify a crypto trade increases `total_fees` by `pct × notional` and an equity trade leaves it unchanged.
- [x] 2.2 Thread the asset class into every `record_trade` caller: `ai_portfolio/service.py` build (`_apply_build_trades`) and rebalance (`_apply_rebalance_trades`) — pass/propagate the in-scope `asset_classes` map and look each ticker's class up per trade; the stop-loss and scope-change-close paths pass their local `cls`; the `paper_trading/service.py` scope-change close passes `cls`. Verify mypy + the AI-portfolio service tests still pass.

## 3. Executor cash-buffer fee estimate

- [x] 3.1 In `ai_portfolio/executor.py` change `_reserve_cash_buffer` so its fee-estimate term is the asset-class-aware estimate: `0` when the run has no crypto candidate, else `CRYPTO_FEE_PCT × base` (conservative upper bound), keeping `max(pct_reserve, fee_reserve)`. Replace the `candidate_count` argument with a crypto-presence signal (e.g. `has_crypto: bool` or a crypto-candidate count) and update both call sites in `execute_build` and `execute_rebalance` to pass it. Verify the buffer tests: percentage term dominates in default config; crypto-fee term reserves against the base when the percentage is zeroed; equity-only run reserves no fee.

## 4. Dashboard fee estimate

- [x] 4.1 In `dashboard/service.py` `_range_fees`, replace `count × TRANSACTION_COST_USD` with a sum of `CRYPTO_FEE_PCT × notional` over the range's trades whose ticker belongs to a crypto-category asset (join/filter via `Asset`); equity trades contribute zero; update the docstring. Verify a session with mixed equity/crypto trades reports a range fee equal to the crypto trades' pct×notional only.

## 5. KPI swap: daily average transaction cost → daily average orders

- [x] 5.1 In `paper_trading/service.py`, rename `SessionKpis.daily_avg_transaction_cost` → `daily_avg_orders: float | None` and compute it in `session_kpis` as `count_session_trades(session, session_id) / len(snapshots)` when snapshots exist, else `None` (reuse the existing `count_session_trades` helper and the already-fetched `snapshots`; drop the `total_fees / len(snapshots)` line). Update both the dataclass docstring and the inline comment.
- [x] 5.2 In `api/schemas.py` rename `PaperTradingSessionKpisRead.daily_avg_transaction_cost` → `daily_avg_orders` (update the docstring), and in `api/routers/paper_trading.py` update the explicit KPI mapping (`daily_avg_orders=kpis.daily_avg_orders`).
- [x] 5.3 In `frontend/src/types/api.ts` rename the `PaperTradingSessionKpis` field to `daily_avg_orders: number | null`; in `PaperTradingSessionPage.tsx` swap the tile to "Daily avg. orders" rendering the value as a number (e.g. two decimals) with a "not yet available" state when `null` and a hint like "Orders per snapshot day" / "Needs a snapshot day"; keep the ten-tile `lg:grid-cols-5` two-row layout. Also correct the adjacent "Transaction fees" tile hint (`$1 per executed trade`) to the asset-class-aware model (e.g. "0.25% on crypto notional; equities free").

## 6. Daily-run learning snapshot order count

- [x] 6.1 In `ai_portfolio/service.py` `_build_run_document`, add `"orders_count": len(trades)` to the assembled document alongside `"orders"`; update the docstring. (JSONB `document` — no migration; a no-run day records `0`.)

## 7. Historical backfill (one-time data-only migration)

- [x] 7.1 Add a new Alembic revision `migrations/versions/<rev>_restate_asset_class_aware_fees.py` with `down_revision = "f0a1b2c3d4e5"` (current head). It restates history data-only — **no `op.add_column`/`drop_column`/schema DDL**. Hardcode the literals `CRYPTO_FEE_PCT = 0.0025` and `HISTORICAL_FLAT_FEE = 1.0` in the migration (do NOT import runtime `settings` or ORM models; use `sa.table`/`sa.column` or raw SQL so the migration is frozen against later code changes).
- [x] 7.2 `upgrade()`: for each paper-trading session, recompute `new_fee` per `PaperTrade` as `CRYPTO_FEE_PCT × quantity × COALESCE(filled_price, price)` for crypto trades and `0.0` for equity; classify crypto by joining the trade's ticker to the `assets` table (`category` is crypto), defaulting to equity when the ticker is unresolvable. Set `paper_trading_sessions.total_fees = Σ new_fee`.
- [x] 7.3 `upgrade()`: re-derive each session's value snapshots in `snapshot_date` order — `cumCorr(D) = Σ (HISTORICAL_FLAT_FEE − new_fee)` over trades with `executed_at::date ≤ D`; set `total_value += cumCorr`, `cash_value += cumCorr` (positions value unchanged); recompute `daily_pnl = new_total_value − contributed − baseline` (baseline = prior snapshot's new `total_value`, or `allocated_capital − Σ capital-event amounts` for the first; `contributed` = Σ capital-event amounts in the window, matching `record_value_snapshot`) and `daily_pnl_pct = daily_pnl / baseline if baseline > 0 else 0.0`.
- [x] 7.4 `downgrade()`: restore the flat-fee history — recompute `total_fees = HISTORICAL_FLAT_FEE × trade_count` per session and re-derive snapshots with the inverse correction (`cumCorr(D) = Σ (new_fee − HISTORICAL_FLAT_FEE)`), OR document it as a non-reversible data migration with an explanatory `raise` — choose the reversible form if feasible. Verify `alembic upgrade head` then `downgrade -1` round-trips cleanly and `alembic check` reports no drift.

## 8. Tests

- [x] 8.1 Add/adjust `record_trade` fee tests: crypto charges `pct × notional`; equity charges nothing; two crypto trades accrue both fees; filled-price notional used when present.
- [x] 8.2 Update existing suites that assumed the flat `$1` fee — valuation (`total_fees`), executor cash-buffer exact-quantity asserts (pin `CRYPTO_FEE_PCT = 0` and `REBALANCE_CASH_BUFFER_PCT = 0` where exact quantities are asserted), dashboard range fees — to the new expected amounts.
- [x] 8.3 Add executor buffer tests for the new fee-estimate term (crypto-present vs equity-only; percentage-zeroed crypto reserve) and a dashboard `_range_fees` crypto-only test.
- [x] 8.4 Replace the daily-avg-cost KPI tests with `daily_avg_orders` tests (backend service + `test_paper_trading_api.py`: orders ÷ snapshot days; `None` without snapshots) and update the session-page vitest (`PaperTradingSessionPage.test.tsx` fixtures/assertions) for the renamed field and the orders tile.
- [x] 8.5 Assert the assembled daily-run `document` includes `orders_count` (equal to the number of the day's filled orders; `0` on a no-run day) in the daily-run snapshot tests.
- [x] 8.6 Add a backfill migration test over a mixed equity/crypto session with recorded trades and value snapshots: after `upgrade`, `total_fees == Σ (CRYPTO_FEE_PCT × crypto notional)`, each snapshot's `total_value`/`cash_value` is lifted by the cumulative removed-fee correction as of its date (positions value unchanged), and `daily_pnl`/`daily_pnl_pct` are recomputed from the corrected series; assert idempotence (re-running `upgrade` logic yields the same values).

## 9. Verification gates

- [x] 9.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` all green.
- [x] 9.2 Confirm no `TRANSACTION_COST_USD` or `daily_avg_transaction_cost` references remain anywhere (repo-wide grep is clean). Exactly one new migration was added (the data-only fee-restatement revision off head `f0a1b2c3d4e5`); confirm it adds/drops no columns and that `alembic upgrade head` → `downgrade -1` round-trips and `alembic check` reports no schema drift.
- [x] 9.3 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build` all green.
