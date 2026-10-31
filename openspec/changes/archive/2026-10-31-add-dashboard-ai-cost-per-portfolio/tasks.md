## 1. Backend — batched cost helper

- [x] 1.1 Add `session_ai_costs_usd(session_ids)` to `backend/src/cadence/paper_trading/ai_cost.py`: one grouped query over `"LiteLLM_SpendLogs"` summing `spend` by the `cadence_session_id` metadata key for the given ids; reuse the cached read-only engine and `_normalize_url`.
- [x] 1.2 Preserve the degradation contract: empty `LITELLM_DATABASE_URL` → `None`; any query error → log warning + `None`; empty `session_ids` → `{}` without a DB hit; reachable → `{sid: float(sum)}` (absent ids = no spend). Keep `session_ai_cost_usd` unchanged.
- [x] 1.3 Unit-test the helper with the LiteLLM engine stubbed/offline (match existing `ai_cost` tests): grouping/map result, ids filter, empty-DSN degradation, error degradation, NULL/empty sum handling, empty-ids short-circuit.

## 2. Backend — dashboard service + schema + endpoint

- [x] 2.1 Add frozen dataclasses to `backend/src/cadence/dashboard/service.py` (e.g. `PortfolioAiCost`, `DashboardAiCosts`) and a `get_dashboard_ai_costs(session)` function: list ACTIVE sessions via `paper_trading_service.list_sessions(session, status=SessionStatus.ACTIVE, ...)` (stopped/archived excluded), resolve each portfolio's display label (same source the dashboard/paper-trading pages use), call `session_ai_costs_usd` once, assemble rows + total per the null/zero semantics, sort rows by cost descending.
- [x] 2.2 Add `DashboardPortfolioAiCostRead` + `DashboardAiCostsRead` to `backend/src/cadence/api/schemas.py` mirroring the dataclasses (`ai_cost_usd: float | None`, `total_ai_cost_usd: float | None`).
- [x] 2.3 Add `GET /dashboard/ai-costs` to `backend/src/cadence/api/routers/dashboard.py` (no `range` param; `db` dependency only) with explicit mapping from the dataclass to the read schema.
- [x] 2.4 Unit-test the service function + endpoint: per-portfolio rows, grand total, excludes stopped/archived sessions, label source, descending order, cost-unavailable (null) degradation vs zero-spend ($0), empty-portfolios case.

## 3. Frontend — types + hook

- [x] 3.1 Add `DashboardPortfolioAiCost` and `DashboardAiCosts` types to the Dashboard section of `frontend/src/types/api.ts`.
- [x] 3.2 Add `getDashboardAiCosts()` + `useDashboardAiCosts()` to `frontend/src/api/dashboard.ts` (query key under `dashboardKeys`, `refetchInterval: 30_000`), as a separate fetch from the overview.

## 4. Frontend — panel + placement

- [x] 4.1 Add a dashboard panel component (e.g. `frontend/src/components/dashboard/AiCostBreakdown.tsx`): one row per portfolio (label + cost) sorted by cost descending, a total row, `formatCurrency` for values, `null → "—"` with a "Cost tracking unavailable" hint, `$0.00` for readable-zero, and an empty state. Match existing dashboard/panel Tailwind styling.
- [x] 4.2 Render the panel in `frontend/src/pages/dashboard/DashboardPage.tsx` directly above the market-performers tiles (the Universe section's `UniversePerformers` best/worst performers), in its own band/section (NOT under "Performance · {range}"), independent of `range` and `selectedIds`.
- [x] 4.3 Vitest for the panel: renders rows sorted desc + total, em-dash + hint on unavailable, `$0.00` on zero, empty state; add/extend dashboard fixtures and the hook wiring test.

## 5. Verify

- [x] 5.1 Backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 5.2 Frontend gates: `cd frontend && npm run typecheck && npm run test && npm run build` (match the repo's actual script names).
- [x] 5.3 `openspec validate add-dashboard-ai-cost-per-portfolio --strict` passes.
