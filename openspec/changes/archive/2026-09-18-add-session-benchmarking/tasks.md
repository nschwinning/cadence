## 1. Catalog & config

- [x] 1.1 Add a `Benchmark` StrEnum (ids) + a mapping to display name and fetch symbol in `paper_trading/constants.py` for all eight indexes (SP500…WILSHIRE_5000). Verify a unit test asserts every enum member has a name and a symbol and that `SP500` maps to `^GSPC`.
- [x] 1.2 Add `DEFAULT_BENCHMARK: str = "SP500"` to `config.py`; verify it resolves to a valid `Benchmark` id in a `uv run python -c` check.

## 2. Schema & migration

- [x] 2.1 Add non-nullable `benchmark: Mapped[str]` (`server_default="SP500"`) to `PaperTradingSession` and a new `BenchmarkPrice` model (`benchmark`, `price_date`, `close`, unique `(benchmark, price_date)` + index) in `paper_trading/models.py`. Verify `uv run mypy src/cadence` stays clean.
- [x] 2.2 Create an Alembic migration (down_revision = current head `d4b7e2f9a1c6`) that creates `benchmark_prices` and adds `benchmark` nullable → backfills all sessions to `'SP500'` → sets NOT NULL; downgrade drops the column and table. Verify `uv run alembic upgrade head` then `downgrade -1` round-trips and `uv run alembic check` reports no drift.

## 3. Benchmark price ingestion

- [x] 3.1 Add a service op that, given a `MarketDataProvider`, fetches each catalog benchmark's `fetch_history(symbol)` and upserts every returned daily bar into `benchmark_prices` (idempotent per benchmark+date), skipping any benchmark whose fetch raises. Verify a service test with the fake provider asserts rows are upserted for all benchmarks, a re-run does not duplicate, and one failing benchmark does not abort the others.
- [x] 3.2 Add the cron-guarded endpoint `POST /ai-portfolio/fetch-benchmarks` (X-Cron-Token, `MarketDataProviderDep`) returning a count summary. Verify an API test asserts 200 + upserted counts with a valid token and 401/403 without one.

## 4. Benchmark computation (read-time, from stored prices)

- [x] 4.1 Add a helper that loads a benchmark's stored closes for a session into a sorted date→close map and resolves a date to the last close on or before it (null when none). Verify a unit test covers exact-date, prior-trading-day, and pre-series cases.
- [x] 4.2 Add a function returning the rebased benchmark value per snapshot date (`allocated * close(d)/close(start)`), with nulls when the series is unavailable. Verify a unit test checks first-snapshot equals allocated capital and graceful nulls when no prices are stored.

## 5. Value-history read

- [x] 5.1 Extend the value-history service read to attach the rebased benchmark value (from stored prices) to each returned snapshot item; null when unavailable. Verify a service test asserts benchmark values are present and correctly rebased, and null when no prices are stored.
- [x] 5.2 Add `benchmark_value: float | None` to the value-history item schema in `api/schemas.py`. Verify the value-history API test asserts each item carries `benchmark_value`.

## 6. KPIs read

- [x] 6.1 Extend `SessionKpis` + `session_kpis` to compute `benchmark_return_pct` (benchmark buy-and-hold fractional return over the session period, from stored prices) and `excess_return_pct` (`total_return_pct − benchmark_return_pct`), both null when unavailable; include the session's `benchmark`. Verify a service test asserts the values and the null-on-unavailable case.
- [x] 6.2 Add `benchmark`, `benchmark_return_pct`, `excess_return_pct` to the KPIs response schema (router constructs it explicitly). Verify the KPIs API test asserts the new fields.

## 7. Build flow & change-benchmark

- [x] 7.1 Add optional `benchmark: Benchmark | None` to `AIPortfolioBuildRequest`, thread through `AIBuildParams`; the build service defaults to `settings.DEFAULT_BENCHMARK` and passes it to `create_session(...)` (new required `benchmark` kwarg). Update all `create_session` call sites/tests. Verify a build-service test asserts the created session's benchmark (default SP500 when omitted; the chosen id when supplied).
- [x] 7.2 Add a service op + domain errors to change a session's benchmark (validate id against the catalog → invalid error; unknown session → not-found). Verify a service test asserts the change persists, an unknown session raises not-found, and an invalid id raises the validation error and leaves the benchmark unchanged.
- [x] 7.3 Add `PUT /paper-trading/sessions/{id}/benchmark` mapping the domain errors to 404/422 and returning the updated session; add `benchmark: str` to `PaperTradingSessionRead`. Verify an API test asserts a successful change returns the new benchmark, 404 for unknown, 422 for an invalid id.
- [x] 7.4 Add `GET /paper-trading/benchmarks` returning the catalog `[{id, name}]`. Verify an API test asserts all eight benchmarks are listed.

## 8. Daily report (Pushover)

- [x] 8.1 Extend `snapshot_all_sessions` so each session's report line includes its benchmark return and excess return (from stored prices), omitting the benchmark suffix when unavailable. Verify a service test asserts the report text includes the benchmark comparison for a session with stored prices and omits it gracefully when absent.

## 9. Ops / cron sidecar

- [x] 9.1 Add a benchmark-ingestion job to the docker-compose `cron` sidecar with a new `BENCHMARK_SCHEDULE` env, scheduled before `SNAPSHOT_SCHEDULE`, curling `/ai-portfolio/fetch-benchmarks` with the cron token; document both in `.env.example`. Verify the generated crontab/script includes the new job (inspect the sidecar entrypoint output).

## 10. Frontend

- [x] 10.1 Add benchmark types to `types/api.ts`: build request `benchmark?`, value-history item `benchmark_value: number | null`, session `benchmark: string`, KPIs `benchmark` + `benchmark_return_pct` + `excess_return_pct`, and a catalog type. Verify `npm run typecheck` passes.
- [x] 10.2 Add a benchmarks catalog client + change-benchmark mutation in `api/paperTrading.ts` (invalidate the session, KPIs, and value-history keys on success). Verify a vitest asserts the mutation posts to the benchmark endpoint and invalidates the right keys.
- [x] 10.3 Overlay the benchmark line on `SessionValueChart` (second series from `benchmark_value`, omitted when all null). Verify a vitest asserts the benchmark line renders when values are present and is absent when null.
- [x] 10.4 Add benchmark-return and excess-return KPI tiles to the session detail KPI row (identify the benchmark; sign-colour excess return; "not yet available" when null). Verify a vitest asserts both tiles render with values and the unavailable state.
- [x] 10.5 Add a benchmark switcher to the session detail view (catalog dropdown, current preselected, progress + error handling, refreshes benchmark figures on success). Verify a vitest asserts changing the selection calls the mutation and reflects the new benchmark.
- [x] 10.6 Add a benchmark selector (default S&P 500, from the catalog) to the AI build form and send `benchmark` with the build request. Verify a vitest asserts the default is S&P 500 and the selected id is included in the submitted payload.

## 11. Verification

- [x] 11.1 Backend: `uv run ruff check . && uv run mypy src/cadence && uv run pytest` all green (including new benchmark tests).
- [x] 11.2 Frontend: `npm run typecheck && npx vitest run && npm run build` all green.
- [x] 11.3 `openspec validate add-session-benchmarking --strict` passes; migration round-trip + `uv run alembic check` clean.
