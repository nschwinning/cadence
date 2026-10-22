## 1. Configuration

- [x] 1.1 Add `LITELLM_DATABASE_URL: str = ""` to `config.py` settings (default empty = cost KPI disabled, independent of `LITELLM_BASE_URL`); verify `uv run mypy src/cadence` passes and a unit test confirms the default is empty.

## 2. Attribution (gateway + rebalance)

- [x] 2.1 Generalize `agents/gateway.py` so the trace context carries a metadata mapping (keep `cadence_trace_id`, add `cadence_session_id` + `cadence_portfolio_id`); `run_config_for_trace()` serializes all present keys into the `x-litellm-spend-logs-metadata` header. Verify with updated `test_agents_gateway.py` asserting the header JSON includes the session/portfolio ids when set and only the trace id otherwise.
- [x] 2.2 Thread the session id + portfolio id from `ai_portfolio/flows/rebalance.py` into the trace at the rebalance agent call site. Verify with an updated `test_ai_portfolio_agent.py` assertion that the run config's spend-log metadata carries the session and portfolio ids.
- [x] 2.3 Confirm recommender and universe-eval call sites remain trace-id-only (no session/portfolio metadata). Verify by inspecting/adding a test that their `run_config_for_trace()` metadata has no `cadence_session_id`.

## 3. Cost read path

- [x] 3.1 Add a read-only LiteLLM-spend helper (lazily-built read-only engine from `LITELLM_DATABASE_URL`) exposing `session_ai_cost_usd(session_id) -> float | None` that `SELECT SUM(spend)` from `LiteLLM_SpendLogs` filtered by `metadata->'spend_logs_metadata'->>'cadence_session_id'`; isolate the table name + metadata-key coupling behind this one helper with a comment. Verify with unit tests: returns `None` when the URL is empty, returns the summed cost on a stubbed/seeded source, and returns `None` (never raises) on a query/connection error.

## 4. Surface the KPI

- [x] 4.1 Add `ai_cost_usd: float | None` to the `SessionKpis` dataclass and populate it in `paper_trading/service.py::session_kpis` via the helper, wrapped so a failure yields `None` without affecting other KPIs. Verify with a `session_kpis` test: KPI present when the helper returns a value, `None` when it returns `None`/raises, other KPIs unchanged.
- [x] 4.2 Add `ai_cost_usd: float | None` to `PaperTradingSessionKpisRead` and the explicit router mapping. Verify with a router/schema test that the field round-trips.
- [x] 4.3 Add `ai_cost_usd: number | null` to the TS `PaperTradingSessionKpis` type and render an "AI cost" tile in the session-detail Performance KPI group (USD format; `—` when null), reusing the compact `KpiTile`/`StatTile` pattern. Verify with a Vitest test: tile shows the formatted USD amount when set and an em dash when null.

## 5. Verification

- [x] 5.1 Backend gate: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` all green.
- [x] 5.2 Frontend gate: `cd frontend && npm run typecheck && npm run test && npm run build` all green.
- [x] 5.3 Confirm `LITELLM_DATABASE_URL` is never surfaced in any read model or the system-status report (grep + a test asserting it is absent from serialized responses).
