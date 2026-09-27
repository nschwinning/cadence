## 1. Schema & migration

- [x] 1.1 Add `use_technical_indicators: Mapped[bool]` (non-nullable, `default=False`, `server_default="false"`) to `PaperTradingSession` in the paper-trading models, mirroring `rebalance_prompt_version`.
- [x] 1.2 Add an Alembic migration with `down_revision` = current head (`c3d4e5f6a7b8`): add the column with `server_default="false"`, backfill existing rows to `false`; `downgrade` drops the column.
- [x] 1.3 Drop the persistent `cadence_test` database so conftest `create_all` rebuilds it with the new column.
- [x] 1.4 Verify the migration round-trips (`alembic upgrade head` then `downgrade`), and confirm existing rows read `false`.

## 2. Build request & session creation

- [x] 2.1 Add an optional `use_technical_indicators: bool = False` field to `AIPortfolioBuildRequest`.
- [x] 2.2 Add the flag to `AIBuildParams` and thread it from the request through to `create_session`.
- [x] 2.3 Persist the flag in `create_session` so it is frozen on the session at build time.

## 3. Conditional trend gating (build & rebalance)

- [x] 3.1 In `run_build_event`, read the flag from the build params and only apply the trend gate/annotations in the build candidate assembly when it is true; otherwise present every in-scope candidate unannotated.
- [x] 3.2 In `run_rebalance_event`, read the frozen `session.use_technical_indicators` and pass it down; treat a session with no persisted value as opted out.
- [x] 3.3 Gate `_candidates_from_universe` on the flag — apply the trend hard-filter + annotations only when opted in. (Driven by `apply_gate=gating_enabled`, which now folds in the flag.)
- [x] 3.4 Gate `_build_holdings` on the flag — attach indicator/reversal context only when opted in. (Driven by `holding_snapshots`, None when `gating_enabled` is false.)
- [x] 3.5 Confirm that when opted out, `trend_context` stays `None` so no per-run trend-decision context is recorded (no extra handling needed downstream). (Both assignments guarded by `if gating_enabled:`.)

## 4. Read schema & API surface

- [x] 4.1 Expose `use_technical_indicators` (read-only) on `PaperTradingSessionRead`.
- [x] 4.2 Confirm the field surfaces in the session read endpoint(s).

## 5. Frontend

- [x] 5.1 Add `use_technical_indicators?: boolean` to the `AIPortfolioBuildRequest` type and `PaperTradingSession` type.
- [x] 5.2 Add a default-off toggle to the AI build form and send the value with the build request.
- [x] 5.3 Confirm the run-detail trend-decision section still hides itself when context is absent (opted-out sessions), no new guard required. (RunDetailPage guards `{data.event.trend_context && <TrendDecisionCard/>}`.)

## 6. Tests

- [x] 6.1 Build: opted-in session applies the trend gate/annotations (existing behavior) — assert candidates are filtered and trend-decision context is recorded. (Existing trend tests updated to opt in.)
- [x] 6.2 Build: opted-out session (default) applies no gate, presents all in-scope candidates unannotated, records no trend-decision context. (`test_run_build_event_opted_out_ignores_trend_gate`.)
- [x] 6.3 Rebalance: opted-in session hard-filters candidates and attaches holdings indicator/reversal context (existing behavior). (`_seed_gated_session` updated to opt in.)
- [x] 6.4 Rebalance: opted-out session applies no gate and attaches no indicator/reversal context; a session with no persisted flag is treated as opted out. (`test_run_rebalance_event_opted_out_ignores_trend_gate` + pre-v3 legacy test.)
- [x] 6.5 `create_session` persists the flag; `PaperTradingSessionRead` exposes it. (`test_run_build_event_persists_opt_in_flag`.)
- [x] 6.6 Frontend: build form toggle defaults off and sends the value; typecheck/vitest/build pass.

## 7. Verification

- [x] 7.1 `uv run ruff check . && uv run mypy src/cadence && uv run pytest` all green.
- [x] 7.2 `openspec validate make-technical-indicators-opt-in --strict` passes.
