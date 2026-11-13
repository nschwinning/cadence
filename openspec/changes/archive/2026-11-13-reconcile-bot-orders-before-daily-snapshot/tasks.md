## 1. Backend

- [x] 1.1 `run_bot_snapshots` reconciles bot-owned journal records first (failure-isolated) and returns snapshots + reconciled counts; `BotSnapshotResponse.reconciled`; router maps it. Verify with pytest: a submitted bot buy that filled at the fake broker is booked before the snapshot (snapshot includes the position, cash reduced, record booked, response `reconciled == 1`); a reconciliation exception still snapshots every active bot; existing snapshot tests updated for the new return type.

## 2. Verification

- [x] 2.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 2.2 `openspec validate reconcile-bot-orders-before-daily-snapshot --strict` passes.
