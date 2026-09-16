## 1. Config & constant

- [x] 1.1 Add `TRANSACTION_COST_USD: float = 1.0` to `settings` in `src/cadence/config.py` (near `SHARPE_RISK_FREE_RATE`).

## 2. Schema & migration

- [x] 2.1 Add `total_fees: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")` to `PaperTradingSession` in `paper_trading/models.py` (after `total_pnl`).
- [x] 2.2 Create Alembic migration (`down_revision = 'c3f6a9d1e0b4'`, new head): add `total_fees` nullable → backfill `SET total_fees = 0 WHERE total_fees IS NULL` → `alter_column` to NOT NULL.
- [x] 2.3 In the same migration, define module-level `_V2_INSTRUCTIONS` (v1 instructions text + a sentence describing the ~$1 per-executed-trade cost and avoiding low-value churn) and `_V2_INPUT_TEMPLATE` (copied verbatim from v1), then `op.bulk_insert` a `rebalance_prompt` row with `version=2`. `downgrade` drops the `total_fees` column and deletes the `version=2` row.

## 3. Fee accounting in the service

- [x] 3.1 In `record_trade` (`paper_trading/service.py`), after persisting the trade, increment the owning session's `total_fees` by `settings.TRANSACTION_COST_USD` (single choke point; charges every executed/recorded trade).
- [x] 3.2 In `compute_session_value`, change the total to `total_value = allocated_capital + total_pnl - total_fees + unrealized_total` (read `total_fees` from the session row). Confirm `cash_value` still derives from `total_value`.
- [x] 3.3 Leave `record_closed_position` realised P&L and `update_session_last_run` `total_pnl` unchanged (fees stay separate; realised P&L stays gross).

## 4. KPI surface

- [x] 4.1 Add `total_fees` to the `SessionKpis` dataclass and populate it (`= session_row.total_fees`) in `session_kpis`.
- [x] 4.2 Add `total_fees: float` to `PaperTradingSessionKpisRead` in `api/schemas.py`.

## 5. Frontend

- [x] 5.1 Add `total_fees: number` to the `PaperTradingSessionKpis` type in `frontend/src/types/api.ts`.
- [x] 5.2 Add a "Transaction fees" KPI tile to the KPI row on `PaperTradingSessionPage` (reuse `StatTile` + `formatCurrency`).

## 6. Tests

- [x] 6.1 Backend: `record_trade` increments `total_fees` by `TRANSACTION_COST_USD` per trade (two trades → 2×).
- [x] 6.2 Backend: `compute_session_value` / `session_kpis` return value net of fees and expose `total_fees`; per-position realised P&L stays gross.
- [x] 6.3 Backend: `/kpis` endpoint response includes `total_fees`; new prompt v2 is the active version and a session built now freezes v2 whose instructions mention the cost.
- [x] 6.4 Frontend: KPI row renders the transaction-fees tile with the value from the KPI summary (update fixtures with `total_fees`).

## 7. Verification

- [x] 7.1 Drop `cadence_test` so conftest rebuilds it with the new column; run `uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 7.2 Migration round-trip: `uv run alembic upgrade head` then `downgrade -1` then `upgrade head`; `uv run alembic check` (no drift).
- [x] 7.3 Frontend: `npm run typecheck && npx vitest run && npm run build`.
