# Tasks

## 1. Backend — per-session `benchmark_value`

- [x] 1.1 Add `benchmark_value: float | None` to the `SessionPerformance` dataclass in `backend/src/cadence/dashboard/service.py` (document it as the since-inception contribution-aware benchmark buy-and-hold current value).
- [x] 1.2 In `_session_performance`, compute `benchmark_value` by loading the full benchmark series (`load_benchmark_series(session, session_row.benchmark)`, no range floor) and calling `rebased_benchmark_value(series, contributions=[Contribution(effective_date=c.effective_date, amount=c.amount) for c in contributions], as_of=<today ET date>)`. Return `None` when there are no contributions or `rebased_benchmark_value` returns `None`. Add a brief comment noting this is the contribution-aware (money-weighted) basis, deliberately different from the time-weighted session-detail excess KPI.
- [x] 1.3 Add `benchmark_value: float | None` to the `DashboardSessionPerformance` Pydantic schema in `backend/src/cadence/api/schemas.py`, and map it in whatever builds the response from `SessionPerformance` (e.g. `model_validate`/explicit mapping in `dashboard/service.py` or the router).
- [x] 1.4 Backend tests: extend the dashboard overview/`_session_performance` tests so a session with priceable benchmark closes returns a `benchmark_value` equal to the contribution-aware buy-and-hold current value (reuse existing benchmark fixtures), and a session whose benchmark is unpriceable returns `benchmark_value is None`; assert the overview schema serialises the new field.

## 2. Frontend — types + aggregation helpers

- [x] 2.1 Add `benchmark_value: number | null` to the `DashboardSessionPerformance` type in `frontend/src/types/api.ts`.
- [x] 2.2 In `frontend/src/pages/dashboard/aggregate.ts`, add pure helpers over a list of selected sessions: aggregate contributed capital (Σ `contributions[].amount`), lifetime P&L $ (Σ `current_value` − contributed), since-inception total return % (lifetime P&L ÷ contributed, with a safe `null`/neutral result when contributed ≤ 0), aggregate benchmark value (Σ `benchmark_value`, or `null` when **any** selected session has `benchmark_value === null`), and excess-vs-benchmark % (portfolio return − benchmark return, `null` when benchmark value is `null` or contributed ≤ 0).
- [x] 2.3 Frontend tests for the helpers in `aggregate.test.ts`: total return % and lifetime P&L $ over multiple sessions, zero/negative contributed-capital fallback, aggregate benchmark value + excess %, and `null` propagation when a selected session has `benchmark_value === null`.

## 3. Frontend — four-tile value band

- [x] 3.1 In `frontend/src/pages/dashboard/HeroTiles.tsx`, expand `ValueTiles` to render four `StatTile`s in a full-width grid (`grid-cols-1 sm:grid-cols-2 lg:grid-cols-4`): Total value (existing), Total return % , Lifetime P&L $, and Return vs benchmark %. Apply `signClass` to the three new signed figures; render the vs-benchmark tile in a clear "not yet available" state when the aggregate excess is `null`. Keep the existing "N selected portfolios · point-in-time" hint.
- [x] 3.2 Confirm `DashboardPage.tsx` passes the selected sessions to `ValueTiles` as before (no structural change; the new fields travel on the same per-session objects) and that the live `FreshnessBadge` remains on the band.
- [x] 3.3 Frontend tests (`HeroTiles` test): `ValueTiles` renders four tiles with the correct figures and sign colours over a selected set; the vs-benchmark tile shows "not yet available" when a selected session has `benchmark_value === null`; toggling the selection re-aggregates the four figures from already-fetched data without a refetch (existing dashboard behaviour preserved).

## 4. Verify

- [x] 4.1 Backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 4.2 Frontend gates: `cd frontend && npm run -s typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate expand-dashboard-live-value-band --strict`.
