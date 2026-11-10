## 1. Cost lookup

- [x] 1.1 Refactor `paper_trading/ai_cost.py`: extract `_costs_by_metadata_key(key, values)` (batched query + degradation contract), make `session_ai_costs_usd` delegate to it, and add `trace_ai_costs_usd(trace_ids)` keyed by `cadence_trace_id`. Verify: unit tests with a fake engine/connection (as the existing ai_cost tests do) — trace lookup returns a sum per trace id, omits ids with no spend, returns `{}` for no ids, `None` when unconfigured or when the query raises; the existing session-cost tests still pass unchanged.

## 2. Token usage on runs

- [x] 2.1 Add the nullable `usage` JSONB column to `BotOrchestratorRun`, generate and hand-trim the migration to that column only, and round-trip it on a scratch database. Verify: `upgrade head` → `downgrade -1` → `upgrade head` succeeds; drop the scratch database; drop `cadence_test` so fixtures rebuild it.
- [x] 2.2 Add `RunUsage` / `OrchestratorAgentResult` to `bot_orchestrator/agent.py`; `decide` returns the result with usage read from `result.context_wrapper.usage`; update `FakeOrchestratorAgent` to return a canned usage. Verify: unit test — the production agent maps a fake SDK result's usage into `RunUsage`; existing agent tests updated and passing.
- [x] 2.3 Add `run_trace_id(run_id)` in `runs.py`, use it in `llm_trace`, and store `usage` on the run after the AI answers. Verify: runs tests — a completed run stores the fake usage; a timed-out run and a skipped run store none; the trace id passed to `llm_trace` equals `run_trace_id(run.id)`.

## 3. Read models and API

- [x] 3.1 Add `orchestrator_ai_costs(db, orchestrators)` and `run_ai_costs(runs)` helpers (one cost query each, degrading to `None`); add `ai_cost_usd` to `BotOrchestratorRead` and `usage` + `ai_cost_usd` to the run summary/detail schemas; populate them in the router for list, detail, run list and run detail. Verify: API tests with `trace_ai_costs_usd` monkeypatched — orchestrator cost equals the sum of its runs' costs; a run with no spend reads `0.0`; an unavailable source yields `null` everywhere and still 200; run reads carry the stored usage.

## 4. Dashboard

- [x] 4.1 Extend `get_dashboard_ai_costs` with active orchestrator rows and a total that includes them; extend the response schema. Verify: dashboard service tests — an active orchestrator appears with its summed cost and is in the total; stopped/archived orchestrators are excluded; unavailable source gives null costs and null total; existing portfolio-only tests still pass.
- [x] 4.2 Update the TS types and `AiCostBreakdown` to merge portfolio and orchestrator rows by cost descending, tag orchestrator rows and link them to `/orchestrators/:id`, and show the empty state only when both lists are empty. Verify: vitest — an orchestrator row renders with its tag, link and cost in cost order; the total includes it; the empty state shows only with no rows; unavailable renders "—" with the hint.

## 5. Orchestrator views

- [x] 5.1 Add the AI cost tile to `OrchestratorDetailPage`, tokens and cost on each run row, and an AI cost column on `OrchestratorsPage`. Verify: vitest — the detail page shows the tile and a run's "1,234 tokens · $0.04"; null cost renders "—"; a run without usage shows no token count; the list shows the AI cost column.

## 6. Verification gates

- [x] 6.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` against the 5435 test DB. Verify: all green; tear the Cadence DB container down.
- [x] 6.2 Frontend: `cd frontend && npx vitest run && npx tsc -p tsconfig.app.json --noEmit`. Verify: vitest green; no type errors beyond the three known pre-existing axios-mock errors.
- [x] 6.3 `openspec validate add-orchestrator-ai-cost --strict`. Verify: passes.
