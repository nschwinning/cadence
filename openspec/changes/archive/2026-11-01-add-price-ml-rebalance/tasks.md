## 1. Price-ML package, model, and storage

- [x] 1.1 Add `scikit-learn` to `backend/pyproject.toml` and lock it; verify `uv sync --frozen` resolves an aarch64-compatible wheel and `uv run python -c "import sklearn"` succeeds
- [x] 1.2 Create the `price_ml` package (`models.py`, `service.py`, `errors.py`, `constants.py`); add the `price_ml_signal` table model (one row per asset: `asset_id` FK cascade + unique, `as_of_date`, `horizon_days`, `direction`, `probability`, `recent_oos_accuracy`, `model_version`, `feature_as_of`, `bar_count`); verify `uv run mypy src/cadence` passes on the new package
- [x] 1.3 Add the `price_ml_signal` table Alembic migration (down_revision = current head); verify upgrade/downgrade round-trips against the test DB
- [x] 1.4 Add Pydantic settings: forward horizon (default ~21 trading days), retrain cadence (default weekly), minimum bar count, staleness bound, random seed, model version; verify a unit test reads the defaults

## 2. Feature assembly, training, and walk-forward validation

- [x] 2.1 Implement deterministic feature assembly from stored `technical_indicator` columns + lagged `price_history` returns into a cross-asset matrix, excluding assets below the minimum bar count or missing required features; verify unit tests for row shape, determinism, and insufficient-history exclusion (no fabricated features, no extra market-data fetch)
- [x] 2.2 Implement forward-return labeling (sign of the configured-horizon forward return) and the pooled `HistGradientBoostingClassifier` training (fixed seed); verify a unit test trains on a small synthetic frame and produces per-row probabilities deterministically
- [x] 2.3 Implement purged/embargoed walk-forward evaluation producing a recent out-of-sample accuracy, purging+embargoing samples whose label horizon overlaps the test window; verify unit tests that overlapping labels are purged and that the reported accuracy is deterministic for fixed inputs
- [x] 2.4 Implement model-artifact caching (retrain weekly / infer nightly): persist and reload the trained model with a metadata-compatibility gate; verify unit tests that a non-retrain run reuses the cached model and that an incompatible cache triggers a retrain

## 3. Precompute job, storage, and reads

- [x] 3.1 Implement the precompute service: train-or-reuse, predict per eligible asset, and record one `price_ml_signal` row per asset (replacing the prior row), isolating per-asset failures; verify unit tests for one-row-per-asset replacement, per-asset failure isolation, and empty-universe handling
- [x] 3.2 Add the cron-guarded precompute endpoint (shared `require_valid_cron_token`) and sequence it after the technical-indicators cron; verify a router test rejects a missing/invalid token and computes nothing, and a valid-token test runs the precompute
- [x] 3.3 Implement `get_latest_ml_signal` / `get_latest_ml_signals` batch reads mirroring the TI snapshot seam, plus the staleness-aware "unavailable" resolution; verify unit tests for batch read (omitting assets with no signal) and stale/missing → "unavailable"
- [x] 3.4 Add a `PRICE_ML_SCHEDULE` cron entry to docker-compose/env (matching sibling cron vars), sequenced after the TI schedule; verify the compose config references the new job

## 4. Rebalance prompt integration

- [x] 4.1 Add `PRICE_ML_PROMPT_VERSION = 5` and a seed Alembic migration inserting the price-ML-aware rebalance prompt (prior version's text verbatim + a defensive per-ticker price-ML block section describing it long-only, advisory, surfacing recent OOS accuracy, and tolerating absence); verify the migration round-trips and the seeded template differs from the prior version only by the price-ML section
- [x] 4.2 Add the `paper_trading_sessions.use_price_ml` column migration (non-nullable, default off, `server_default "false"`, down_revision = current head); verify upgrade/downgrade round-trips against the test DB
- [x] 4.3 Thread `use_price_ml` through `AIBuildParams` (field + `to_payload`/`from_payload`) → `create_session` → the session row (build flow persists the flag only, attaches nothing); verify a unit test that a built session records the chosen flag and is frozen
- [x] 4.4 Add the price-ML annotation builder (mirroring `_fundamentals_annotation`: direction, probability, recent OOS accuracy, as-of date; "ML signal unavailable" marker) and attach it in `flows/rebalance.py` to both candidates (`_candidates_from_universe`) and holdings (`_build_holdings`), gated on `use_price_ml` AND frozen version ≥ `PRICE_ML_PROMPT_VERSION`; extend `trend_context` so the run records the price-ML picture; verify unit tests: opted-in on price-ML-aware version attaches to candidates + holdings; opted-out attaches nothing; older frozen version attaches nothing; unavailable signal marked not fabricated; rebalance proceeds when the signal source is down
- [x] 4.5 Confirm the routed initial allocation inherits the price-ML block with no extra wiring (it runs as a rebalance); verify a unit test that an opted-in session's initial allocation attaches the price-ML block

## 5. Read model and schemas

- [x] 5.1 Add `use_price_ml` to `PaperTradingSessionRead` (and the build request schema) with explicit router mapping; verify `model_validate` maps the flag and a router test returns it on list and single-session reads
- [x] 5.2 Verify `uv run mypy src/cadence` passes on the schema/router changes

## 6. Frontend

- [x] 6.1 Add `use_price_ml` to the TS `AIPortfolioBuildRequest` and `PaperTradingSessionRead` mirrors; verify `npm run typecheck` passes
- [x] 6.2 Add the "Use price ML" toggle (default off) to `BuildAIPortfolioCard`; verify vitest asserts it defaults off and is sent with the build request when enabled and when left off
- [x] 6.3 Add a session-detail "Price ML" fact tile mirroring the fundamentals tile; verify vitest asserts it reflects the session's flag

## 7. Verification

- [x] 7.1 Run backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` — all green
- [x] 7.2 Run frontend gates: `cd frontend && npm run typecheck && npm run test && npm run build` — all green
- [x] 7.3 Run `openspec validate add-price-ml-rebalance --strict` — valid
