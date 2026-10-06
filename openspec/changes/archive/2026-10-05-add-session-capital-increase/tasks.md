## 1. Capital-events ledger (model + migration)

- [x] 1.1 Add a `SessionCapitalEvent` ORM model in `paper_trading/models.py` (`id` PK, `session_id` FK→`paper_trading_sessions` indexed, `amount` Float NOT NULL, `effective_date` Date NOT NULL, `created_at` DateTime NOT NULL); verify `uv run mypy src/cadence` passes and the model imports cleanly.
- [x] 1.2 Create an Alembic migration `add_session_capital_events` with `down_revision = "b5f1a2c3d4e6"` (confirm the live head first with `uv run alembic heads`); `upgrade` creates the table + `session_id` index, `downgrade` drops them. Verify round-trip: `uv run alembic upgrade head`, `uv run alembic downgrade -1`, `uv run alembic upgrade head`, and `uv run alembic check` reports no drift.

## 2. Contribution model helper

- [x] 2.1 Add a service helper (e.g. `session_contributions(session_row, events)`) in `paper_trading/service.py` returning the ordered contribution set `{(start_date, allocated_capital − Σ amounts)} ∪ {(effective_date, amount) per event}` per design D1; verify a unit test covers a no-event session (single baseline = allocated_capital) and a session with two events (baseline + two rows, baseline = allocated_capital − Σ).

## 3. Increase-capital operation (service + error + schema + router)

- [x] 3.1 Add `InvalidCapitalChangeError` to `paper_trading/errors.py`; verify it subclasses `PaperTradingError`.
- [x] 3.2 Add `increase_session_capital(session, *, session_id, amount)` to `paper_trading/service.py` mirroring `change_session_benchmark`: `get_session`→`SessionNotFoundError`, `amount<=0`→`InvalidCapitalChangeError`, insert a `SessionCapitalEvent`, `allocated_capital += amount`, commit+refresh, return row. Verify a service test: capital rises by the amount, one event row is written, and cash from `compute_session_value` rises by the amount.
- [x] 3.3 Add `SessionCapitalIncreaseRequest { amount: float = Field(gt=0) }` to `api/schemas.py`; add `contributed_capital: float` to `PaperTradingSessionRead` (populated from `allocated_capital`). Verify `PaperTradingSessionRead.model_validate` exposes `contributed_capital`.
- [x] 3.4 Add `POST /api/v1/paper-trading/sessions/{session_id}/capital` to `api/routers/paper_trading.py` calling `increase_session_capital`, returning `PaperTradingSessionRead`; map `SessionNotFoundError`→404 and `InvalidCapitalChangeError`→422. Verify API tests: 200 raises capital + returns the session, 404 unknown session, 422 for amount ≤ 0.

## 4. Time-weighted, contribution-aware analytics

- [x] 4.1 Add a contribution-adjusted daily-return helper in `paper_trading/service.py` building the `r_d` series from the snapshot NAVs and the contribution set (`r_d = (V_d − C_d − V_{d−1})/V_{d−1}`, first `V_{d−1}` = baseline), plus a final live point; verify a unit test against a hand-computed series including a contribution day.
- [x] 4.2 Rework `session_kpis` (`service.py:1573-1653`): `total_return_pct` = chained TWR of the `r_d` series; Sharpe from the same series; `max_drawdown` from the cumulative growth index; keep absolute `total_return = total_value − allocated_capital`; `excess_return_pct = TWR − benchmark_return_pct`. Verify a test that a session with a mid-session contribution does NOT show the contribution as a gain, and a regression test that a no-contribution session's KPIs are unchanged from the simple-return values.
- [x] 4.3 Update the Sharpe computation path so its daily series is the contribution-adjusted `r_d` series (not the raw stored `daily_pnl_pct`); verify a test where a contribution day is excluded from the Sharpe input.
- [x] 4.4 Update `record_value_snapshot` (`service.py:1265-1300`) so the day's P&L subtracts contributions effective on the snapshot date (per design D5); verify a test that a snapshot taken on a contribution day reports P&L excluding the added cash.

## 5. Contribution-aware benchmark overlay

- [x] 5.1 Make `rebased_benchmark_value` in `paper_trading/benchmark.py` contribution-aware: `Σ_c amount × close(t)/close(d_c)` over contributions with `d_c ≤ t` (single contribution ≡ today's rebased value); leave `benchmark_return_fraction` unchanged. Verify a unit test: single contribution matches the old value; a later contribution steps the line up on/after its date.
- [x] 5.2 Thread the session's contribution set into `list_value_history` (`service.py:1356-1387`) and the dashboard narrative benchmark helper (`ai_portfolio/service.py:1795-1798`); verify value-history tests: single-contribution unchanged, and a session with a later contribution shows the stepped benchmark line.

## 6. Frontend

- [x] 6.1 Add `contributed_capital: number` to `PaperTradingSession` in `frontend/src/types/api.ts`; add `changeSessionCapital(sessionId, amount)` raw fn + `useIncreaseSessionCapital(sessionId)` hook (POST `/sessions/{id}/capital`, invalidate `paperTradingKeys.all` + `.kpis(id)` + `.valueHistory(id)`) in `frontend/src/api/paperTrading.ts`. Verify a client test: POSTs to the capital endpoint and invalidates the three keys.
- [x] 6.2 Add an "Add capital" control (numeric amount input + submit button, isPending/isError feedback, rejects non-positive/empty) near the Capital fact tile in `PaperTradingSessionPage.tsx`, mirroring `BenchmarkSwitcher`/`ScopeSwitcher`. Verify component tests: a positive amount POSTs and refreshes; zero/negative/empty does not POST; a failed request surfaces an error.

## 7. Verification

- [x] 7.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` all green (including the new ledger, operation, TWR, and benchmark tests).
- [x] 7.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build` all green.
- [x] 7.3 `openspec validate add-session-capital-increase --strict` passes; manual smoke: build/seed a session, `POST .../capital` with a positive amount, confirm KPIs/value-history reflect the added cash without counting it as a gain, and an amount ≤ 0 is rejected with 422.
