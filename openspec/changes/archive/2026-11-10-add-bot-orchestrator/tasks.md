## 1. Selling stop and provenance (strategy-bots)

- [x] 1.1 Add `StopReason.ORCHESTRATOR` and `BotOrigin.ORCHESTRATOR`; give `stop_bot_session` a `reason` parameter (default manual). Verify: unit test — an orchestrator-reason stop records `stop_reason="orchestrator"` and `stopped_at`; the existing manual-stop test still passes.
- [x] 1.2 Add the flatten pass to `run_tick` (design decision 2): before active sessions, sell every open position of stopped/archived sessions through `ExecutionEngine.exit` with reason "session stopped"; skip it when the market is closed; never evaluate entries for non-active sessions. Verify: service tests — a stopped bot with two positions is flat after one open-market tick, with two sells in its ledger and the status still stopped; an archived bot with a leftover position is flattened; nothing is sold while the market is closed; a stopped bot never opens a position.
- [x] 1.3 Give `create_bot_session` keyword-only `origin` and `orchestrator_id`; add `orchestrator_id` / `orchestrator_label` to `BotSessionRead` (and the TS `BotSession` type). Verify: service test — orchestrator origin and id are persisted; API test — a manual create still reports origin manual with a null orchestrator.

- [x] 1.4 Add `Broker.is_trading_day(day)` (Alpaca: `/v2/calendar` for that date has a session; `StubBroker`: true; a malformed calendar raises `BrokerError`). Verify: unit tests with faked calendar responses — a session on the date → true, no session (holiday/weekend) → false, a session for another date → false, malformed → raises; the stub returns true.

## 2. Data model and migration

- [x] 2.1 Create the `bot_orchestrator` package with `constants.py` (`OrchestratorStatus`, `OrchestratorRunStatus`, `OrchestratorTrigger`, limit constants: min capital 5,000, min bot capital 1,000, ranges) and `models.py` (`BotOrchestrator`, `BotOrchestratorRun` with the partial unique index on live runs); add `orchestrator_id` (FK + index) and `capital_returned_at` to `BotSession`, plus the relationship. Verify: mypy clean; models import in `cadence.database` metadata.
- [x] 2.2 Generate and hand-trim the Alembic migration to exactly the two tables, the partial unique index and the two `bot_sessions` columns; round-trip it on a scratch database. Verify: `upgrade head` → `downgrade -1` → `upgrade head` succeeds; drop the scratch database afterwards.

## 3. Orchestrator service (lifecycle and capital)

- [x] 3.1 `create_orchestrator` (validation per spec, `free_capital = capital`, no AI), `get_orchestrator`, `list_orchestrators(include_archived)`, `archive_orchestrator` (stopped only), with domain errors. Verify: unit tests — valid create; each invalid field rejected; archive of an active orchestrator rejected.
- [x] 3.2 `settle_returned_capital` (row-locked, idempotent) and computed reads `orchestrator_value` / `allocated_capital` / bot counts. Verify: unit tests — a stopped flat bot returns its cash once; a stopped bot still holding positions is not returned; a second settle changes nothing; value = free + unreturned bots' current value.
- [x] 3.3 `stop_orchestrator`: stop every active bot with reason orchestrator, settle already-flat bots, set stopped. Verify: unit test — both active bots become stopped with reason orchestrator, the orchestrator is stopped, and a flat bot's cash is returned immediately.
- [x] 3.4 Call `settle_returned_capital` for all orchestrators from the bots tick router right after `run_tick`. Verify: API test — after a tick that flattens a stopped orchestrator bot, the orchestrator's free capital includes the bot's cash.

## 4. Briefing builder

- [x] 4.1 `briefing.py`: index technicals from `benchmark_prices` via `compute_snapshot` (volume fields dropped, `unavailable` when too short); sector breadth from `technical_indicator`; sector news tone from `resolve_sentiment_annotations` aggregated per sector (`unavailable` fallback); candidates; presets; running and being-sold bots with performance; limits. Verify: unit tests with seeded rows and a fake sentiment source — breadth shares and counts per sector, unknown-sector bucket, sentiment aggregation and the unavailable path, an index with too few closes is unavailable, running-bot rows carry value and return, limits reflect free capital and open slots; the output is JSON-serialisable.

## 5. Agent

- [x] 5.1 `agent.py`: `OrchestratorDecision` / `StopAction` / `DeployAction` Pydantic models, the prompt renderer (deterministic, `ORCHESTRATOR_PROMPT_VERSION`), the `OrchestratorAgent` Protocol and the `OpenAIOrchestratorAgent` (web_search tool, budget, turns, timeout settings in `config.py`, `llm_trace`, timeout/SDK error → `OrchestratorUnavailableError`); add a `FakeOrchestratorAgent` to `tests/fakes.py`. Verify: unit tests — the prompt includes the limits, presets, running bots and sector sections and is deterministic; the agent is built with the Pydantic output type and the web_search tool; a forced timeout raises `OrchestratorUnavailableError`.

## 6. Decision validation, application and runs

- [x] 6.1 Pure `validate_decision` (stops then deploys against a mutable limit copy; every rejection rule in the spec). Verify: unit tests — stop of a foreign or inactive bot rejected; unknown preset, ineligible ticker, no tickers, duplicate tickers, too many tickers, capital below 1,000, above the per-bot share, above free capital, and no slot left are each rejected with a reason; a stop frees a slot for a later deploy in the same decision.
- [x] 6.2 `execute_run(run_id, agent, broker, notifier)`: settle capital, mark running, skip when today is not a trading day (`broker.is_trading_day`), build and store the briefing, call the agent, validate, apply in one transaction (domain errors from `create_bot_session` → rejected; unexpected errors → rollback and fail), set the status per spec, store decision/applied/rejected/research/duration, and notify on scheduled runs only. Verify: service tests with the fake agent and stub broker — succeeded with one stop plus one deploy (bot created with origin orchestrator, free capital decremented); partial with one over-budget deploy; failed with zero changes on agent timeout; failed when every action is rejected; skipped on a non-trading day; failed (not skipped) when the market calendar is unavailable; a pre-open run's deploy is created before the open and trades only from the first open tick; a no-action decision succeeds; notifications only on scheduled runs.
- [x] 6.3 Due-ness and triggering: `orchestrator_due` via `rebalance_due` anchored on the last succeeded/partial run; `queue_run(trigger)` respecting the one-live-run rule; `OrchestratorJobRunner` (single worker) plus a startup sweep failing orphaned live runs. Verify: unit tests — daily always due; weekly not due within the same ISO week after a counting run; due again after a failed run; monthly boundary; a second `queue_run` while one is live raises; the orphan sweep fails queued/running runs.

## 7. API

- [x] 7.1 Router `api/routers/bot_orchestrators.py` with schemas and dependency seams (agent, runner) for list/create/detail/stop/archive, manual run (202 / 409), run list (paginated) and run detail, and the cron-guarded `run-due` returning started/not-due/already-running counts; register it in the app and run the orphan sweep at startup. Verify: API tests — create 201 and 422 on invalid config; detail carries value/free/allocated and bots; stop stops its bots; archive 409 when active; manual run 202 and 409 when a run is live or the orchestrator is stopped; run-due 403 without a token and starts only due orchestrators; run list newest first with pagination; unknown ids 404.
- [x] 7.2 Add the `ORCHESTRATOR_SCHEDULE` (`0 9 * * 1-5`, before the open) cron script and line to `docker-compose.yml`. Verify: `docker compose config` renders the new cron line without errors.

## 8. Frontend

- [x] 8.1 Types in `types/api.ts` and `api/orchestrators.ts` (query keys, fetchers, list/detail/runs hooks with polling while a run is live, create/stop/archive/run-now mutations invalidating orchestrator and bot dependents). Verify: `npx tsc -p tsconfig.app.json --noEmit` reports no new errors.
- [x] 8.2 Sidebar "Orchestrators" entry after "Bots" with a new icon, and the `/orchestrators` and `/orchestrators/:id` routes. Verify: vitest — the sidebar shows the entry directly after Bots and marks it active on the route.
- [x] 8.3 `OrchestratorsPage` plus the `DeployOrchestratorCard` modal (defaults, validation, navigate on success). Verify: vitest — list rows show label, status, cadence, value, return, bots x/max and last run; the form opens with 3 / 50% / 5 / daily, blocks capital below 5,000, submits the request shape, and navigates to the new orchestrator.
- [x] 8.4 `OrchestratorDetailPage`: capital tiles, configuration, bots table linking to bot detail, run history with expandable market summary and applied/rejected actions, Run now / Stop (confirm) / Archive by status, and polling while a run is live. Verify: vitest — tiles and bots render; the run history shows a partial run's rejected reasons; Run now posts and the view shows the queued run; Stop asks for confirmation before posting; Archive is shown only when stopped.
- [x] 8.5 Bot detail provenance shows "Deployed by {label}" linking to the orchestrator. Verify: vitest — an orchestrator-deployed bot shows the linked label; a manual bot does not.

## 9. Verification gates

- [x] 9.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` against the 5435 Postgres test database (recreate `cadence_test` if its schema is stale). Verify: all green; then tear the Cadence database container down.
- [x] 9.2 Frontend: `cd frontend && npx vitest run && npx tsc -p tsconfig.app.json --noEmit`. Verify: vitest green; no type errors beyond the three known pre-existing axios-mock errors.
- [x] 9.3 `openspec validate add-bot-orchestrator --strict`. Verify: passes.
