## 1. Previous-snapshot accessor

- [x] 1.1 In `backend/src/cadence/paper_trading/service.py`, add a public read-only accessor for a session's most recent value snapshot strictly before a given date, wrapping the existing private `_prior_snapshot` (e.g. `get_previous_value_snapshot(session, *, session_id, before)` returning `SessionValueSnapshot | None`). Verify by inspection that it reuses `_prior_snapshot` (no new query) and returns `None` when the session has no earlier snapshot.
- [x] 1.2 Add a unit test asserting the accessor returns the most recent snapshot with `snapshot_date < before` (skipping gaps/weekends), and `None` when none exists.

## 2. Daily-change holdings for the push

- [x] 2.1 In `backend/src/cadence/ai_portfolio/snapshots.py::snapshot_all_sessions`, replace the `holdings` build that reads `pos["return_pct"]` with a daily-change build: fetch the session's previous snapshot via the new accessor using the current snapshot's `snapshot_date`; for each held ticker in the current snapshot compute `today_price / prior_price − 1` where `prior_price` is that ticker's `price` in the previous snapshot. Match by ticker.
- [x] 2.2 Apply the exclusion/omission rules: when there is no previous snapshot, build an empty holdings list (line omitted); exclude any ticker absent from the previous snapshot or whose prior price is missing or `<= 0`; a resulting empty list omits the best/worst line (relying on `_best_worst_line`'s existing `if not holdings` guard). Do not change `_best_worst_line` or `_session_snapshot_message` behavior.
- [x] 2.3 Confirm by inspection that the snapshot document's per-position `return_pct` and every other consumer of `snapshot.positions` are untouched.

## 3. Tests for the push metric

- [x] 3.1 Add a test that two sessions holding the same ticker at different `avg_cost`, snapshotted on the same day with a prior snapshot present, produce the **same** daily-change value for that ticker in each session's holdings (and that it equals the day-over-day price move, not a since-entry return).
- [x] 3.2 Add a test that a session with no prior snapshot sends a push with **no** best/worst line, and that a session whose only movable holding was opened that day (absent from the prior snapshot) also omits the line while other comparable holdings are still ranked.
- [x] 3.3 Add/adjust a notification-level assertion that the best/worst line reflects the computed daily changes (best = max, worst = min) and no longer reflects `avg_cost`. Update any existing snapshot/notification test that assumed the since-entry performer line.

## 4. Verification gates

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` all green.
- [x] 4.2 Frontend only if touched (none expected): not applicable unless a frontend file changes.
- [x] 4.3 `openspec validate fix-daily-pnl-performer-metric --strict` passes.
