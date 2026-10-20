## 1. Model catalog (backend)

- [x] 1.1 Add an `AIModel` `StrEnum` + display-name map + accessor in `backend/src/cadence/paper_trading/constants.py`, mirroring `Benchmark`/`BENCHMARK_DISPLAY_NAMES`/`benchmark_display_name`, with the confirmed starter members — `gpt-5-mini` ("GPT-5 Mini", the session-column backfill value for pre-existing sessions), `gpt-5.6-luna` ("GPT-5.6 Luna"), `gpt-6-luna` ("GPT-6 Luna", the configured default for new builds); verify a unit test maps every member to a non-empty display name
- [x] 1.2 Add `ModelCatalogEntry{id,name}` to `schemas.py` (mirror `BenchmarkCatalogEntry`) and a `GET /paper-trading/models` endpoint returning the catalog, mirroring `GET /paper-trading/benchmarks`; verify an endpoint test lists all catalog ids with their display names and includes the configured default
- [x] 1.3 Change `config.py` `AI_PORTFOLIO_MODEL` from `gpt-5-mini` to `gpt-6-luna` (the new default for builds that omit a model and the agent fallback); verify a test reads the new default
- [x] 1.4 Add a test asserting BOTH the configured default id (`settings.AI_PORTFOLIO_MODEL` = `gpt-6-luna`) AND the session-column backfill id (`gpt-5-mini`) are members of the `AIModel` catalog, so neither a new nor a backfilled session holds an unselectable id

## 2. Accept, resolve, and freeze the model on the session (backend)

- [x] 2.1 Add `model: AIModel | None` to `AIPortfolioBuildRequest` in `schemas.py` (mirror the `benchmark` field) so an out-of-catalog id yields an automatic 422; verify a request test posts an unknown model id and gets 422
- [x] 2.2 Add `model` to `AIBuildParams` (`ai_portfolio/params.py`) incl. `to_payload`/`from_payload`, and resolve the default in the build router (`ai_portfolio.py`) as `payload.model.value if payload.model is not None else settings.AI_PORTFOLIO_MODEL`, mirroring benchmark resolution; verify a params round-trip unit test preserves the model
- [x] 2.3 Thread `model=params.model` into `create_session` (`flows/build.py` + `paper_trading/service.create_session` row assembly), mirroring `benchmark`; verify a build test persists the chosen model on the session and a build omitting the model persists the configured default (`gpt-6-luna`)

## 3. Session `model` column + migration (backend)

- [x] 3.1 Add a non-nullable `model` column on `paper_trading_sessions` in `paper_trading/models.py`, mirroring the `benchmark` column; verify `uv run mypy src/cadence` passes
- [x] 3.2 Add an Alembic migration (down_revision `e8f3a1c5d2b4`, the current head) adding the column with `server_default=sa.text("'gpt-5-mini'")` and non-nullable, mirroring `d7e2f9a4c1b3_add_use_fundamentals_session_column.py`; verify `alembic upgrade head` then `downgrade -1` round-trips cleanly and existing rows backfill to `gpt-5-mini`

## 4. Run AI on the session's frozen model (backend)

- [x] 4.1 Add an optional `model` parameter to the agent rebalance seam: `agent.rebalance` Protocol + `OpenAIAIPortfolioAgent.rebalance` + `rebalance_ai_portfolio` + `_run_rebalance` in `ai_portfolio/agent.py`, replacing the hardcoded `settings.AI_PORTFOLIO_MODEL` at the agent-build site with the passed model, falling back to `settings.AI_PORTFOLIO_MODEL` when absent; verify a unit test with a fake agent captures the model argument reaching the build site
- [x] 4.2 Read `session_row.model` in `flows/rebalance.py` and pass it into the agent rebalance call (covers both the opening allocation and daily rebalances, since route-initial drives both through this path); verify a rebalance test asserts the session's frozen model reaches the agent and that a session with no frozen model falls back to the configured default

## 5. Record the model per run (backend)

- [x] 5.1 Add a nullable scalar `model` column to `AIPortfolioEvent` (`ai_portfolio/models.py`) and an Alembic migration chained after the session-column migration; verify upgrade/downgrade round-trips and historical events read null
- [x] 5.2 Set the event's `model` at event finalization (`_finish_event` in `ai_portfolio/_helpers.py`) from the run's resolved model (NOT via `run_stats`); verify a rebalance test asserts the recorded event carries the model that produced the run

## 6. Expose the model in reads (backend)

- [x] 6.1 Add `model: str` to `PaperTradingSessionRead` (`schemas.py`) with the router mapping from the session row, mirroring `benchmark`; verify a session-read test returns the session's model
- [x] 6.2 Add `model: str | None` to the run-detail read (`AIPortfolioRunDetail`/`AIPortfolioEventRead` in `schemas.py`, mirroring `rebalance_prompt_version`) with the router mapping; verify a run-detail test returns the model that produced the run

## 7. Frontend

- [x] 7.1 Add TS types in `frontend/src/types/api.ts`: `ModelCatalogEntry`, `model` on `PaperTradingSession` and `AIPortfolioBuildRequest`, and `model` on the run-detail type; verify `npm run -s typecheck` passes
- [x] 7.2 Add `listModels`/`useModels` client + hook in `frontend/src/api/paperTrading.ts`, mirroring `listBenchmarks`/`useBenchmarks` with its own query key; verify `npm run -s typecheck` passes
- [x] 7.3 Add a model `<select>` (state + payload wiring) to `BuildAIPortfolioCard.tsx`, mirroring the benchmark select, defaulting to the configured default; verify a vitest test renders the catalog options and submits the chosen model in the build payload
- [x] 7.4 Add a read-only "Model" fact tile to `PaperTradingSessionPage.tsx` resolving the id to its display name via the model catalog (mirror the benchmark name resolution and the Company-fundamentals tile); verify a vitest test renders the session's model display name
- [x] 7.5 Add a "Model" tile to `RunDetailPage.tsx`, mirroring the Prompt-version tile, sourced from the run-detail `model`; verify a vitest test renders the run's model

## 8. Spec sync + verification gates

- [x] 8.1 Run backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` — all green
- [x] 8.2 Run frontend gates: `cd frontend && npm run -s typecheck && npx vitest run && npm run build` — all green
- [x] 8.3 `openspec validate add-per-session-ai-model --strict` passes; then spec-sync the ai-paper-trading + app-shell deltas into the main specs and archive the change (via the archive workflow, which syncs + moves it)
