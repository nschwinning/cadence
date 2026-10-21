## 1. Backend — benchmark overlay floor covers the earliest contribution

- [x] 1.1 In `dashboard/service.py::get_dashboard_overview`, extend `overlay_floor` to the minimum of the windowed session value-point dates **and** every active session's contribution effective dates: `contribution_dates = [c.effective_date for perf in sessions for c in perf.contributions]`, `overlay_floor = min([*session_point_dates, *contribution_dates], default=None)`. Leave contributions and `_benchmark_overlays` otherwise untouched.
- [x] 1.2 Update the `_benchmark_overlays` docstring so it states the price window covers the earliest contribution (not just the earliest windowed value point), so every contribution is priceable by the client.

## 2. Backend — tests

- [x] 2.1 Dashboard-overview test (reusing the existing dashboard test fixtures + StubBroker): with ≥2 active sessions where one opened **before** the range start (its earliest snapshot/contribution precedes the earliest range-windowed value point), assert each returned benchmark overlay's `points` include a close whose date is **on or before** that session's earliest contribution effective date — i.e. `overlay_floor <= earliest contribution date` — so every contribution is priceable.
- [x] 2.2 `Max`-range regression test: the benchmark overlay floor/points are unchanged by the fix (folding contribution dates into an already-unwindowed floor does not move it), confirming the change is a no-op for `Max`.
- [x] 2.3 Confirm the frontend `aggregate.test.ts` still passes unchanged; if any assertion encodes the old (too-narrow) floor, revisit it — no frontend source change is expected.

## 3. Verify

- [x] 3.1 Backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 3.2 Frontend gates only if any frontend file was touched: N/A — no frontend source changed (only re-ran `aggregate.test.ts`, which passed unchanged). `cd frontend && npm run -s typecheck && npx vitest run && npm run build`.
- [x] 3.3 `openspec validate fix-dashboard-benchmark-early-contribution-pricing --strict` passes.
