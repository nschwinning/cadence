## 1. Backend — compute and expose the KPI

- [x] 1.1 Add `daily_avg_transaction_cost: float | None` to the `SessionKpis` dataclass in `backend/src/cadence/paper_trading/service.py` (document it in the docstring).
- [x] 1.2 In `session_kpis`, compute `daily_avg_transaction_cost = session_row.total_fees / len(snapshots)` when `snapshots` is non-empty, else `None` (reuse the already-fetched `snapshots`); set it on the returned `SessionKpis`.
- [x] 1.3 Add `daily_avg_transaction_cost: float | None = None` to `PaperTradingSessionKpisRead` in `backend/src/cadence/api/schemas.py` (mirror field placement near `total_fees`).
- [x] 1.4 Map the new field in the explicit `PaperTradingSessionKpisRead(...)` construction in `get_session_kpis` (`backend/src/cadence/api/routers/paper_trading.py`).

## 2. Backend — tests

- [x] 2.1 In `backend/tests/test_paper_trading_service.py`, assert `session_kpis` returns `total_fees / snapshot_count` for a session with snapshots, and `None` when there are no snapshots.
- [x] 2.2 In `backend/tests/test_paper_trading_api.py`, assert the `/sessions/{id}/kpis` response includes `daily_avg_transaction_cost` (numeric with snapshots; null without).
- [x] 2.3 Run `uv run ruff check . && uv run mypy src/cadence && uv run pytest` from `backend/` and fix any failures.

## 3. Frontend — type and tile

- [x] 3.1 Add `daily_avg_transaction_cost: number | null;` to the `PaperTradingSessionKpis` interface in `frontend/src/types/api.ts` (near `total_fees`).
- [x] 3.2 In `KpiRow` (`frontend/src/pages/paper-trading/PaperTradingSessionPage.tsx`), add a "Daily avg. transaction cost" `StatTile` immediately after the "Transaction fees" tile: show `formatCurrency(data.daily_avg_transaction_cost)` with a per-snapshot-day hint when present, and a "Not yet available" fallback when `null`.

## 4. Frontend — KPI tile redesign

- [x] 4.1 Change the Performance group grid to five columns on wide viewports (`lg:grid-cols-5`, keeping `grid-cols-1 sm:grid-cols-2`) so its 10 tiles form two rows.
- [x] 4.2 Reduce the shared `StatTile` size in `frontend/src/components/dashboard/StatTile.tsx` (smaller padding, value font, and label font) so both KPI groups are more compact; audit other `StatTile` consumers (e.g. the dashboard) and keep them legible — use a size variant/prop if a global shrink regresses another page.

## 5. Frontend — tests and verification

- [x] 5.1 Update `frontend/src/pages/paper-trading/PaperTradingSessionPage.test.tsx` KPI fixtures (`KPIS`, `KPIS_NO_RISK_DATA`) to include `daily_avg_transaction_cost`, and assert the new tile renders its value and its "not yet available" fallback.
- [x] 5.2 Run `npm run typecheck && npx vitest run && npm run build` from `frontend/` and fix any failures.

## 6. Change validation

- [x] 6.1 Run `openspec validate add-daily-avg-cost-kpi --strict` and resolve any issues.
