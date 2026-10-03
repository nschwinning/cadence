## 1. Prompt schema + crypto-scoped prompt (D6)

- [x] 1.1 Add a `kind` discriminator to the rebalance-prompt model (values `rebalance`, `crypto_rebalance`), with version monotonic per kind and "active = highest version within a kind"; verify `uv run mypy src/cadence` passes and the model imports.
- [x] 1.2 Add a non-nullable `crypto_rebalance_prompt_version` column to the paper-trading session model; verify the model imports and mypy passes.
- [x] 1.3 Write an Alembic migration (following `a7b8c9d0e1f2_seed_rebalance_prompt_v3.py`): add `kind` defaulting existing rows to `rebalance`; seed `crypto_rebalance` v1 with crypto-scoped instructions + input template (template keeps `{risk_profile}`, `{holdings_json}`, `{account_json}`, `{candidates_json}`; instructions state only the crypto sleeve is rebalanced within the provided crypto budget and equities will not trade); add `crypto_rebalance_prompt_version` backfilled to the seeded active crypto version. Verify `uv run alembic upgrade head` then `downgrade`, and `uv run alembic check` reports no drift.
- [x] 1.4 Add a service loader for the active/ frozen crypto-rebalance prompt by version + kind, failing with a clear error when absent; verify a unit test covers found and missing-version cases.

## 2. Freeze the crypto prompt at build time

- [x] 2.1 In the AI build flow, capture the active `crypto_rebalance` prompt version onto the new session column alongside the existing rebalance-prompt freeze; verify a build test asserts the column is set to the active crypto version.
- [x] 2.2 Expose the frozen crypto prompt version on the session read schema/model as the existing frozen version is exposed; verify the session read test includes it.

## 3. Crypto-only rebalance run path (D2, D3, D4, D5)

- [x] 3.1 Thread a `crypto_only` flag through `run_rebalance_event` (and the job runner entry) so a run can be started in crypto-only mode; verify the function signature change compiles and existing callers default to the full-portfolio behavior.
- [x] 3.2 In crypto-only mode, intersect `allowed_categories` with `{CRYPTO}` regardless of the session's `asset_types`, and restrict BOTH the candidate/target set AND the considered current holdings to crypto so equities are never assigned a target (D3); verify a test that a mixed session's crypto-only run produces only crypto candidates.
- [x] 3.3 Compute the `crypto_budget` = Σ(crypto position market value) + `compute_session_value().cash_value`, and pass it into `execute_rebalance` as the base capital for the crypto-only run; verify a service/unit test that the budget equals crypto value + unallocated cash (not allocated capital).
- [x] 3.4 Keep the no-crypto short-circuit: a crypto-only run for a session with no crypto held or targeted records a SKIPPED run and does NOT invoke the agent; verify a test asserts the agent is not called.
- [x] 3.5 Select the session's frozen crypto-scoped prompt for the crypto-only run (task 1.4 loader), failing cleanly if missing; verify a test asserts the crypto prompt is used and the missing-prompt error path.
- [x] 3.6 Build `account_summary` from the session's derived `cash_value` (instead of global broker buying power) for all rebalances, and additionally include the `crypto_budget` for crypto-only runs; verify a test asserts `account_summary` carries session cash (and crypto budget in crypto-only mode).

## 4. Executor crypto-budget sizing (D3, D4)

- [x] 4.1 Add a crypto-only sizing mode to `execute_rebalance`/`_rebalance_crypto` that sizes crypto targets against the passed `crypto_budget` as base capital, never `allocated_capital`, and never emits equity orders or sells held equities; verify a unit test that crypto target value is derived from the crypto budget and equity positions are left untouched.
- [x] 4.2 Verify, via an end-to-end-style service test, that a crypto-only rebalance of a mixed stocks+crypto session leaves every equity position unchanged and only places crypto orders.

## 5. Weekend crypto-only cron endpoint (D1, D7)

- [x] 5.1 Add `POST /ai-portfolio/rebalance-crypto-daily` guarded by `require_valid_cron_token`, mirroring `rebalance-daily` targeting (active DAILY_REBALANCING AI sessions, defer unsettled build orders, skip already-running) but starting crypto-only jobs and skipping no-crypto sessions before the agent; return triggered/skipped counts with distinct skip reasons (already running, awaiting build fill, no crypto). Verify router tests cover valid-token trigger, invalid/empty-token rejection, and the no-crypto skip reason.
- [x] 5.2 Ensure the crypto-only run reuses the daily-rebalance notification path, labelled as a crypto-only run; verify a test that a crypto-only run submitting orders sends a notification and a skipped run does not.

## 6. Unallocated-cash KPI (D8)

- [x] 6.1 Add the session's unallocated cash (`cash_value`) to `PaperTradingSessionKpisRead`, sourced from the already-computed `compute_session_value` inside `session_kpis`; verify a KPI test asserts the field equals current value minus positions value.

## 7. Deploy / config (D1, D7)

- [x] 7.1 Add a `crypto-rebalance.sh` script and a `crypto` cron entry to `docker-compose.yml` (default `CRYPTO_REBALANCE_SCHEDULE "35 9 * * 6,0"`, `CRON_TZ` America/New_York) sending the `X-Cron-Token`, mirroring the existing rebalance cron; verify the compose file parses (`docker compose config`).
- [x] 7.2 Add a manual-trigger helper under `scripts/` (mirror `run-rebalance.sh`) and document `CRYPTO_REBALANCE_SCHEDULE` in `.env.example` and `README.md`; verify the docs mention the weekend crypto cadence and the new endpoint.

## 8. Frontend: unallocated-cash tile

- [x] 8.1 Add the unallocated-cash field to the KPI type in `types/api.ts` and the paper-trading KPI client; verify `npm run typecheck` passes.
- [x] 8.2 Add an unallocated-cash KPI tile to the session detail view (money amount), alongside the existing tiles; verify a co-located Vitest test renders the tile from a KPI fixture.

## 9. Verification

- [x] 9.1 Backend: `uv run ruff check . && uv run mypy src/cadence && uv run pytest` all green.
- [x] 9.2 Migration round-trip: `uv run alembic upgrade head` then `downgrade`, and `uv run alembic check` clean.
- [x] 9.3 Frontend: `npm run typecheck && npx vitest run && npm run build` all green.
- [x] 9.4 `openspec validate add-weekend-crypto-rebalance --strict` passes.
