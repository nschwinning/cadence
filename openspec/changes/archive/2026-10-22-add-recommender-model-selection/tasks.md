## 1. Persist the model on the run

- [x] 1.1 Add `model: Mapped[str]` (non-nullable) to `RecommendationRun` in `recommendations/models.py`. Create an Alembic migration (down_revision = current head) that adds `recommendation_runs.model` as `String NOT NULL` with a `server_default` of the configured default model string, then drops the `server_default`; downgrade drops the column. Verify the migration round-trips (upgrade → downgrade) against the test DB.

## 2. Accept + validate the model on the request

- [x] 2.1 Add `model: AIModel | None = None` to `RecommendationRunCreate` in `api/schemas.py` (import `AIModel` from `paper_trading/constants.py`); add `model: str` to `RecommendationRunRead`. Verify `uv run mypy src/cadence` passes and a schema test confirms an unknown model id is rejected and a valid one is accepted.
- [x] 2.2 In `api/routers/recommendations.py`, pass the requested model (or `None`) through to run creation; an unknown model id yields 422 (enum validation). Verify with a router test: valid model → 202 with the model on the run; unknown model → 422 and no run created; omitted model → 202 defaulting to the configured model.

## 3. Resolve the default + thread to the agent

- [x] 3.1 In `recommendations/service.py::create_run`, resolve `None` → `settings.RECOMMENDER_MODEL` and persist it on the run. In `execute_run`, read `run.model` and pass it to `agent.recommend(...)`. Verify with a service test that the persisted/used model is the selected one, and the configured default when omitted.
- [x] 3.2 Add a `model: str` parameter to the `RecommenderAgent.recommend(...)` protocol and `OpenAIRecommenderAgent._run(...)` in `recommendations/agent.py`, passing it into `build_agent(model=...)`. Update `StubRecommenderAgent` (`recommendations/stub.py`) and the test fakes (`tests/fakes.py`) to accept and record the model. Verify with an agent/fake test that `build_agent` receives the selected model for both the universe and watchlist targets.

## 4. Surface on the frontend

- [x] 4.1 Add the `model` field to the TS recommendation run request + read types (mirror the Pydantic schemas). Add a model `<select>` to the recommend and watchlist run-create forms, populated from the existing `GET /paper-trading/models` catalog and defaulted to the configured default recommender model; submit the chosen model. Surface the run's model on the run detail/list. Verify with a Vitest test: the form renders the selector defaulted correctly and submits the chosen model, and the run display shows the model used.

## 5. Verification

- [x] 5.1 Backend gate: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` all green.
- [x] 5.2 Frontend gate: `cd frontend && npm run typecheck && npm run test && npm run build` all green.
- [x] 5.3 Confirm back-compat: existing callers/tests that POST a recommendation run without a `model` still succeed and default to the configured model (grep for such call sites / run the recommendations test suites). Verified: `test_create_run_defaults_model_to_configured_default` + `test_create_defaults_model_to_configured_recommender_model` cover the omitted-model path; the full suite (949 passed) exercises every existing no-`model` call site unchanged.
