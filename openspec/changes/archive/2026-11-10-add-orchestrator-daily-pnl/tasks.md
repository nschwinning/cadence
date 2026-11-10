## 1. Bot push roll-up (strategy-bots)

- [x] 1.1 Rename `_bot_daily_pnl` to public `bot_daily_pnl` (update callers) and send the per-bot daily push only when `bot.orchestrator_id is None`, while still snapshotting every active bot. Verify: service tests — a manual bot is snapshotted and pushed; an orchestrator-deployed bot is snapshotted but not pushed; the existing daily-summary tests still pass.

## 2. Orchestrator snapshots

- [x] 2.1 Add `BotOrchestratorSnapshot` (unique `(orchestrator_id, snapshot_date)`) to `bot_orchestrator/models.py`; generate and hand-trim the migration to that table; round-trip it on a scratch database. Verify: `upgrade head` → `downgrade -1` → `upgrade head` succeeds; drop the scratch database and the stale `cadence_test`.
- [x] 2.2 `record_orchestrator_snapshot(db, orchestrator, snapshot_date)` (settle, compute figures, upsert) and `previous_orchestrator_snapshot` / `first_orchestrator_snapshot` reads. Verify: unit tests — the snapshot carries value, free, allocated and active bots; a second call on the same date updates rather than duplicates; previous/first lookups return the right rows.

## 3. Daily push

- [x] 3.1 Pure `orchestrator_daily_message(...)` builder in `bot_orchestrator/daily.py` (value + day change, total return, capital line, optional benchmark line, best/worst bot line, decision line) reusing the bot formatting helpers. Verify: unit tests — day change vs previous snapshot and vs the pool on day one; percent omitted for a non-positive baseline; benchmark line present/omitted; best+worst, single "Only bot", and no-bot cases; started line with preset/tickers/capital and "none"; stopped line with orchestrator and kill-switch reasons, return, and "none"; lists capped at five with "+N more"; decision line for succeeded, partial, failed (truncated error), skipped, and no run.
- [x] 3.2 `run_orchestrator_daily(db, *, notifier, now)`: for each active orchestrator, record the snapshot, gather best/worst bot P&L from today's bot snapshots, the bots started (`created_at`) and stopped (`stopped_at`) on today's America/New_York date, today's newest run, the benchmark return since the first snapshot, and send the push best-effort. Verify: service tests — one push per active orchestrator with the expected title and lines; a bot deployed today appears under Started and a bot stopped today by its kill-switch appears under Stopped with "kill-switch"; bots started or stopped on other days are not listed; stopped orchestrators get no snapshot or push; a raising notifier does not fail the job; no notifier still records snapshots.

## 4. Router

- [x] 4.1 Call `run_orchestrator_daily` from `/bots/snapshot-daily` after `run_bot_snapshots`; add `orchestrator_snapshots` to `BotSnapshotResponse`. Verify: API test — with one manual bot and one orchestrator with a bot, the job returns both counts, sends exactly two pushes (the manual bot's and the orchestrator's), and records the orchestrator snapshot.

## 5. Verification gates

- [x] 5.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` against the 5435 test DB. Verify: all green; tear the Cadence DB container down.
- [x] 5.2 `openspec validate add-orchestrator-daily-pnl --strict`. Verify: passes.
