# Tasks

## 1. Backend: comparison read

- [x] 1.1 Add `list_sessions_value_comparison(db)` to `paper_trading/service.py` that lists non-archived sessions (reusing `list_sessions(include_archived=False)`) and, per session, loads its ordered value snapshots (reusing `list_value_snapshots`), returning a per-session series with `session_id`, `label` (`portfolio_name or strategy_key`), `allocated_capital`, and points `{snapshot_date, total_value}` oldest-first; verify a unit test that two non-archived sessions each return their ordered points, an archived session is excluded, and a session with no snapshots returns an empty points list
- [x] 1.2 Add `SessionValueComparisonPoint`, `SessionValueComparisonSeries`, and `SessionValueComparisonResponse` schemas to `api/schemas.py`; verify they serialize a series (including empty points) via a schema/round-trip test or the endpoint test below

## 2. Backend: endpoint

- [x] 2.1 Add `GET /sessions/value-history-comparison` to `routers/paper_trading.py` (mounted under `/api/v1/paper-trading`, thin: call service → build `SessionValueComparisonResponse`), ordered so it does not collide with the existing `/sessions/{session_id}/...` routes; verify an API test that the endpoint returns 200 with one entry per non-archived session, excludes archived sessions, and includes a snapshot-less session with empty points

## 3. Frontend: data layer

- [x] 3.1 Add `SessionValueComparisonPoint`, `SessionValueComparisonSeries`, and `SessionValueComparisonResponse` types to `types/api.ts` mirroring the backend schemas; verify `npm run typecheck` passes
- [x] 3.2 Add `listSessionsValueComparison()`, a `paperTradingKeys.valueComparison()` query key, and a non-polling `useSessionsValueComparison()` hook to `api/paperTrading.ts`; verify a Vitest test that the client calls the correct URL and returns the parsed response

## 4. Frontend: comparison chart component

- [x] 4.1 Create `pages/paper-trading/SessionComparisonChart.tsx` — a dependency-free inline-SVG multi-line chart mirroring `SessionValueChart` (viewBox 800×160, non-scaling stroke), with a `%`/`$` metric toggle defaulting to return %, one distinctly-colored polyline per session that has ≥2 points on a shared calendar x-domain and a per-metric shared y-domain, a legend mapping color→label (including legend-only entries for sessions with <2 points), and an insufficient-data placeholder when no session has ≥2 points; return % = `(total_value − allocated_capital) / allocated_capital` (guarded on `allocated_capital > 0`); reuse `Panel`, `formatCurrency`, `formatPercent`; verify co-located Vitest tests for: multi-line render + legend, toggle switches metric/rescales, <2-point session is legended not plotted, placeholder when no plottable session, and loading/error states
- [x] 4.2 Render `SessionComparisonChart` on `pages/paper-trading/PaperTradingPage.tsx` above the Sessions card; verify a Vitest test that the list page shows the comparison chart panel

## 5. Verification

- [x] 5.1 Run `uv run ruff check . && uv run mypy src/cadence && uv run pytest` and confirm all green
- [x] 5.2 Run `npm run typecheck && npx vitest run && npm run build` in the frontend and confirm all green
- [x] 5.3 Run `openspec validate add-session-comparison-chart --strict` and confirm it passes
