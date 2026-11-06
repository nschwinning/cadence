## 1. Backend — surface market state on the overview

- [x] 1.1 Add a `market_open: bool` field to the `DashboardOverview` dataclass in `backend/src/cadence/dashboard/service.py` and verify `mypy src/cadence` stays clean.
- [x] 1.2 In `get_dashboard_overview`, populate `market_open` by calling `broker.is_market_open()` wrapped so any exception falls back to `True` (mirroring the `_market_is_open` default-open convention); do not touch any value-computation path. Verify by reading the diff that only the new field is added.
- [x] 1.3 Add `market_open: bool` to the `DashboardOverviewRead` Pydantic schema in `backend/src/cadence/api/schemas.py` and confirm the router (`api/routers/dashboard.py`) passes the broker through unchanged (no new endpoint).

## 2. Backend — tests

- [x] 2.1 Add a service test: `get_dashboard_overview` reports `market_open == True` with a fake broker whose `is_market_open()` returns True, and `False` when it returns False.
- [x] 2.2 Add a service test: a fake broker whose `is_market_open()` raises still yields a successfully-built overview with `market_open == True` (documented fallback), no exception propagated.
- [x] 2.3 Verify the schema round-trips the field (overview read includes `market_open`); run `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` — all green. (Start the Postgres test DB on port 5435 for this run and tear it down after.)

## 3. Frontend — surface the market-state label

- [x] 3.1 Add `market_open: boolean` to the `DashboardOverview` type in `frontend/src/types/api.ts` to mirror the backend schema.
- [x] 3.2 Add a market-state badge in the `DashboardPage.tsx` header (beside `HealthIndicator`), following the dot+label `role="status"` pattern: green dot + "Market open" when `market_open`, neutral/grey dot + "Market closed" otherwise, driven by the overview payload.

## 4. Frontend — tests

- [x] 4.1 Add a Vitest test rendering the dashboard with `market_open: true` asserting a "Market open" `role="status"` label, and one with `market_open: false` asserting "Market closed".
- [x] 4.2 Run `cd frontend && npx vitest run && npx tsc --noEmit` — all green.

## 5. Verification

- [x] 5.1 Confirm no change to `compute_session_value`, EOD-vs-live gating, crypto-live pricing, strategy-bot valuation, total-value aggregation, or the 30s refetch cadence (diff review); run `openspec validate add-dashboard-market-state-indicator --strict`.
