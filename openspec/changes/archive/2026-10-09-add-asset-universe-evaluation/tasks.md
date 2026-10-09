## 1. Persistence (model + migration)

- [x] 1.1 Add `AssetUniverseEvaluation` ORM model to `assets/models.py` (table `asset_universe_evaluation`: `id`, `narrative` Text, `strengths`/`concerns`/`suggestions` JSONB, `fingerprint` String not-null, `model` String nullable, `generated_at` tz-aware DateTime) and verify it imports cleanly (`uv run python -c "import cadence.assets.models"`).
- [x] 1.2 Create an Alembic migration with `down_revision = "e9f0a1b2c3d4"` creating the table; verify `uv run alembic upgrade head` then `uv run alembic downgrade -1` round-trips and `uv run alembic check` reports no drift.

## 2. Evaluation agent seam

- [x] 2.1 Add `UniverseEvaluationOutput` (narrative, strengths, concerns, suggestions) and a `UniverseEvaluationAgent` Protocol + `OpenAIUniverseEvaluationAgent` (tool-less `build_agent`, `asyncio.run(Runner.run(..., max_turns=1))` under `asyncio.wait_for`, model `settings.RECOMMENDER_MODEL`) in a new `assets/universe_agent.py`, mirroring `recommendations/agent.py`; include a pure `build_universe_evaluation_prompt(summary)`. Verify module imports and a prompt-builder unit test passes.
- [x] 2.2 Add `FakeUniverseEvaluationAgent` to `tests/fakes.py` returning a canned `UniverseEvaluationOutput` and recording calls; verify a test can instantiate and call it offline.

## 3. Service logic

- [x] 3.1 Implement `_universe_summary(assets)` (counts by category/sector, eligibility counts, top concentrations, total, foreign/unpriceable NULL-`alpaca_symbol` listings) in `assets/service.py`; verify a unit test asserts the summary for a small fixture universe.
- [x] 3.2 Implement deterministic `_universe_fingerprint(assets)` (SHA-256 over canonical ticker-sorted serialization of mutable columns); verify unit tests: identical universes hash equal; add/remove, metric change, and eligibility change each change the hash; price/order-independent.
- [x] 3.3 Implement `generate_evaluation(session, agent, assets)` (build summary → call agent → upsert the single row with content, fingerprint, model, generated_at) and `get_evaluation(session)` / staleness compare; add `AssetEvaluationUnavailableError` to `assets/errors.py`. Verify tests: generate persists one row; regenerate replaces it; outdated=false when unchanged, true after an asset change; empty universe returns none without calling the agent; agent failure raises the error and leaves any existing row intact.

## 4. API layer

- [x] 4.1 Add `AssetUniverseEvaluationRead` (narrative, strengths, concerns, suggestions, generated_at, outdated) and a nullable response envelope to `api/schemas.py`; verify `model_validate` maps from the ORM row in a unit test.
- [x] 4.2 Add routes to `api/routers/assets.py`: `GET /assets/universe-evaluation` (lazy-fill when empty + non-empty universe, compute `outdated`) and `POST /assets/universe-evaluation/refresh` (regenerate+replace), with a `get_universe_evaluation_agent()` DI factory; map `AssetEvaluationUnavailableError` → HTTP 502. Verify API tests (agent faked via DI override): GET on empty DB generates+returns; second GET does not regenerate; GET flags outdated after an asset mutation; POST refresh regenerates; empty universe returns null and never calls the agent; agent failure returns 502.

## 5. Frontend

- [x] 5.1 Add TS types (`AssetUniverseEvaluation`, response envelope) to `types/api.ts` and a typed client `api/assetEvaluation.ts` (query-key, `getEvaluation`, `refreshEvaluation`, `useAssetUniverseEvaluation` query + `useRefreshAssetUniverseEvaluation` mutation invalidating the query). Verify `npm run typecheck` passes.
- [x] 5.2 Add `UniverseEvaluationPanel.tsx` rendering the narrative as paragraphs + the three finding arrays as bulleted lists, the `generated_at` time, an outdated warning badge when `outdated`, and a Refresh button (disabled + spinner while pending); show a generating state while the initial GET is loading and an error state on failure. Verify co-located Vitest tests: renders narrative + findings + generated_at; outdated badge only when outdated; refresh button triggers the mutation and shows loading; first-load shows generating state.
- [x] 5.3 Render `UniverseEvaluationPanel` in `AssetsPage.tsx` directly below the composition donuts (after the donut grid block, ~line 467); verify `AssetsPage.test.tsx` still passes and the panel appears under the donuts.

## 6. Verification gates

- [x] 6.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` all green (incl. the new agent/service/API tests).
- [x] 6.2 Migration round-trip: `cd backend && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head && uv run alembic check` clean.
- [x] 6.3 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build` all green.
