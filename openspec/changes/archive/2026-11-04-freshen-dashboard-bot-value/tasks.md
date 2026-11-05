## 1. Backend — live bot value on the overview

- [x] 1.1 In `backend/src/cadence/strategy_bots/service.py` `dashboard_performance`, source the row's point-in-time `current_value` and `unrealised` from `latest_value_observation(session, bot)` instead of `snapshots[-1]`: when an observation exists use its `total_value`/`unrealised_pnl`; when it is `None` fall back to cost-marked `total_value(bot, {})` with `unrealised = 0.0`. Leave the daily-snapshot value **series** (`points`), the `value_start` baseline, `contributions`, the benchmark value, `realised_pnl`/`fees`, and `kind='bot'` untouched. Verify by reading the function back: the value series and baseline still come from snapshots while `current_value`/`unrealised` come from the observation.

## 2. Backend tests

- [x] 2.1 In `backend/tests/test_strategy_bots_dashboard.py` (reusing the existing bot factories and an intraday value-point helper), add a test: a bot whose latest intraday `bot_value_point` is newer than its latest daily snapshot reports that point's `total_value` as `current_value` and its `unrealised_pnl` as `unrealised_pnl` on the `dashboard_performance` row (not the snapshot value), while the plotted series stays the daily snapshot. Verify the test passes.
- [x] 2.2 Add a test: with only daily snapshots (no newer value point) the row's `current_value` equals the latest snapshot value; with neither snapshots nor points it falls back to the cost-marked value with `unrealised_pnl == 0.0`. Verify the test passes.
- [x] 2.3 Add a test asserting the range `pnl` tracks the live `current_value` (i.e. `pnl == current_value - value_start` with the freshest-observation `current_value`). Verify the test passes.

## 3. Verification

- [x] 3.1 Run backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` — all green (ruff ✓, mypy ✓ 130 files, 1211 pytest passed).
- [x] 3.2 Frontend: no change needed — the change is backend-only and the leaderboard already renders `current_value` uniformly, so no component or fixture was touched and the frontend suite is unaffected.
- [x] 3.3 Run `openspec validate freshen-dashboard-bot-value --strict` and confirm it reports valid.
