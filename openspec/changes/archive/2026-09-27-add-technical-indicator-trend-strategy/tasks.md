# Tasks

## 1. `technical-indicators` package: compute engine
- [x] 1.1 Create `backend/src/cadence/technical_indicators/` package with `__init__.py`.
- [x] 1.2 Add `constants.py`: indicator periods (SMA 50/200, EMA 20, MACD 12/26/9, RSI 14 Wilder, ROC 120, Bollinger 20/2σ, hvol 20, avg_vol 50, 52w high, 252d drawdown) and **tunable gate thresholds** + divergence/slope lookbacks.
- [x] 1.3 Add `compute.py` (ported from quantara, pure pandas/numpy, no TA-Lib): build a close (prefer `adj_close`, fall back to `close`) + volume series from `list[HistoryBar]` and compute the full fixed indicator set; return a result dataclass. Absent values (insufficient history) are `None`, never a failure.
- [x] 1.4 In `compute.py`, derive the deterministic uptrend gate: regime (`close>SMA200 AND SMA50>SMA200 AND SMA200_slope>=0`) AND momentum (`MACD_hist>0 AND RSI14>50 AND ROC120>0`); OBV-rising as soft bonus only; a required-indicator-absent case evaluates the gate to fail.
- [x] 1.5 In `compute.py`, derive the reversal flags (macd_hist_rollover, rsi_rollover, return_decel, obv_price_divergence proxy, sma200_slope_flattening) as booleans.
- [x] 1.6 Unit-test the engine (synthetic uptrend/downtrend/insufficient-history series): gate pass/fail cases, absent-value handling, each reversal flag.

## 2. Storage + migrations
- [x] 2.1 Add `models.py` with `technical_indicator` (one row per asset — unique on asset id; `trading_date`, all nullable indicator columns, gate verdict + sub-verdicts, reversal-flag booleans) and `technical_indicator_run` (status, started/finished, processed/failed counts).
- [x] 2.2 Write Alembic migration 1 creating both tables; `down_revision = e5c9a3f7d2b8`. Confirm single linear head with `alembic heads` first.
- [x] 2.3 Write Alembic migration 2 seeding `rebalance_prompt` v3 (append-only, two-part trend-trading instructions + input template, retaining v2 constraints); `down_revision` = migration 1.
- [x] 2.4 Add a nullable `trend_context` JSONB column to `ai_portfolio_events` (`ai_portfolio/models.py`, alongside `research`) and write Alembic migration 3 modeled on the `research` column migration (`e1f4c2a7b9d5_...`); `down_revision` = migration 2.
- [x] 2.5 Round-trip all migrations: `alembic upgrade head` then `downgrade`, and `alembic check` (no drift). _(single head `b2c3d4e5f6a7`; up→down→up clean; `alembic check`: no new operations)_

## 3. Service + background runner + cron trigger
- [x] 3.1 Add `service.py`: compute-and-store one asset (delete-then-insert / upsert the single latest snapshot), read latest snapshot(s) by asset id, and a run that iterates the universe committing per asset and recording a `technical_indicator_run` audit; per-asset failures recorded, run continues.
- [x] 3.2 Add the single-worker background runner (`ThreadPoolExecutor(max_workers=1)`, quantara pattern); reject/skip a second concurrent run.
- [x] 3.3 Add a cron-guarded HTTP endpoint under `/api/v1` reusing `require_valid_cron_token`; start the job in the background and return immediately.
- [x] 3.4 Add a nightly busybox-crond schedule entry in docker-compose (run before the market-open rebalance).
- [x] 3.5 Tests: service upsert/replace + read; run audit + per-asset failure isolation; single-worker guard; cron endpoint valid/invalid/empty-token behaviour.

## 4. Wire the trend gate into the trading flows
- [x] 4.1 In `ai_portfolio/service.py`, enrich candidate assembly (`_candidates_from_universe` / helper) to read each in-scope asset's latest snapshot, **drop** assets failing the gate or lacking a snapshot, and annotate survivors with their trend indicators — applied at both build (~278) and rebalance (~540).
- [x] 4.2 Apply the gate to AI-discovered assets before they are offered as candidates.
- [x] 4.3 In `_build_holdings`, attach each holding's full indicator set + reversal flags to the AI payload; do **not** hard-exit any holding.
- [x] 4.4 Update `agent.py` to render the v3 prompt's candidate annotations and holdings indicator/reversal context (no output-schema change).
- [x] 4.5 Tests: candidates failing the gate are absent from `candidates_json`; a candidate with no snapshot is dropped; holdings always carry indicator + reversal payload; output schema unchanged.

## 5. Per-run trend-decision context (persist → expose → render)
- [x] 5.1 In `service.py`, assemble the trend-decision blob (`dropped_candidates` with reasons, surviving-candidate `indicators`, holdings `indicators` + `reversal_flags`) at the candidate/holdings seams for both build and rebalance; pre-declare it before the `try` so a mid-run failure preserves it.
- [x] 5.2 Persist it via `_finish_event` and `_fail_event` (add a kwarg; `if trend_context: event.trend_context = trend_context`), mirroring the `research` pattern; leave it null for runs on a pre-trend frozen prompt version.
- [x] 5.3 Add `trend_context` to `AIPortfolioEventRead` (`api/schemas.py`) so it flows through the run list and run-detail endpoints.
- [x] 5.4 Add `trend_context` (+ a blob interface) to the frontend `AIPortfolioEvent` type (`types/api.ts`).
- [x] 5.5 Add a trend-decision `Card` to `pages/runs/RunDetailPage.tsx` (modeled on `ResearchCard`) showing dropped candidates + reasons and the indicator annotations for survivors and holdings; omit the section when null.
- [x] 5.6 Tests: backend event persists and returns `trend_context` on build and rebalance (and on a mid-run failure); frontend `RunDetailPage` renders the section when present and omits it when null.

## 6. Verification
- [x] 6.1 Backend: `uv run ruff check . && uv run mypy src/cadence && uv run pytest`. _(ruff OK; mypy OK 77 files; pytest 493 passed)_
- [x] 6.2 Frontend: `npm run typecheck && npx vitest run && npm run build`. _(typecheck clean; 80/80 vitest; build OK)_
- [x] 6.3 Confirm v3 becomes the active prompt (highest version) and new builds freeze it while existing sessions keep their frozen version. _(active prompt = v3 in dev DB; freeze behaviour covered by passing `test_run_build_event_freezes_active_prompt_version` + `test_run_rebalance_event_uses_frozen_version`)_
- [ ] 6.4 Manual smoke: trigger the indicator cron with a valid token → snapshots stored + run audit; a build only enters gate-passing assets and the run detail shows the trend-decision section (dropped + handed-over).
