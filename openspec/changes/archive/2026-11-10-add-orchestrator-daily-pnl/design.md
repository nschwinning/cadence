## Context

- **The evening bot job.** `POST /bots/snapshot-daily` (cron 16:15 ET, weekdays) calls
  `strategy_bots.service.run_bot_snapshots`, which for every active bot:
  - marks its positions;
  - records a `BotValueSnapshot`;
  - sends one push built by `notifications._bot_summary_message`, titled
    `Cadence bot: <label> daily P&L`.
- **Bot helpers that already exist:**
  - `_bot_daily_pnl` (day change against the previous snapshot or allocated capital);
  - `_bot_benchmark_returns`, which uses `paper_trading.benchmark.load_benchmark_series`
    and `benchmark_return_fraction`.
- **Orchestrators keep no value history.** `orchestrator_figures` computes value, free
  and allocated capital, and bot counts live.
- **Composition pattern.** The tick router already composes an orchestrator step after a
  bot step (`settle_all_returned_capital` after `run_tick`), which keeps `strategy_bots`
  unaware of orchestrators.

## Goals / Non-Goals

**Goals:**
- One daily push per orchestrator with figures consistent with the other daily pushes.
- Orchestrator bots stop pushing individually; manual bots are unchanged.
- Snapshots that also serve a future orchestrator value chart.

**Non-Goals:**
- A frontend chart, a cron change, a per-orchestrator notification toggle, or archiving
  the stale `add-strategy-bot-notifications` change.

## Decisions

**1. The orchestrator step runs in the bots snapshot router, after the bot snapshots.**
`/bots/snapshot-daily` calls `run_bot_snapshots(...)` and then
`bot_orchestrator.daily.run_orchestrator_daily(db, broker=..., notifier=..., now=...)`.
That order guarantees today's bot snapshots exist when computing each bot's day P&L for
the best/worst line. `BotSnapshotResponse` gains `orchestrator_snapshots: int = 0`.
Rejected: a separate cron job. It would race the bot snapshots and needs another
compose line.

**2. Skipping the bot push is a one-line condition inside `strategy_bots`.**
`run_bot_snapshots` still snapshots every active bot but calls `_notify_safely` only
when `bot.orchestrator_id is None`. This reads the existing column; it needs no import
of the orchestrator package. `_bot_daily_pnl` becomes public as `bot_daily_pnl`, and the
old private name is removed, with callers updated, so the orchestrator step can rank
bots by the same day P&L the bot push used.

**3. `bot_orchestrator_snapshots` table.**
- Columns: `id`, `orchestrator_id` (FK, cascade), `snapshot_date` (date), `value`,
  `free_capital`, `allocated_capital`, `active_bots`, `created_at`.
- Unique on `(orchestrator_id, snapshot_date)`.
- Upserted (select then update or insert, mirroring `record_bot_snapshot`).
- The date is the job's date, the same as the bot snapshots'.

**4. Message (`bot_orchestrator/daily.py`, pure builder plus job).**
Title: `Cadence orchestrator: <label> daily P&L`. Body lines:
```
$10,250.00 today (+$120.00, +1.18%)
Total return: +$250.00 (+2.50%)
Free $4,000.00 · Allocated $6,000.00 · Bots 2/3
vs S&P 500: +0.90% (excess +1.60%)                       ← when closes exist
Best: Turtle Breakout (Algo 25) on MSFT +$85.00 · Worst: RSI Mean Reversion (Algo 16) on AAPL -$12.00
Started: Turtle Breakout (Algo 25) on MSFT, NVDA ($2,500.00)          ← or "Started: none"
Stopped: RSI Mean Reversion (Algo 16) on AAPL — orchestrator (+1.8%); MA Crossover (Algo 6) on XOM — kill-switch (-5.2%)   ← or "Stopped: none"
Decision run: partial                                     ← or "No decision run today"
```
- **Day change:** against the previous orchestrator snapshot, falling back to the
  capital pool on day one. The percentage is omitted when the baseline is not positive.
- **Total return:** against the capital pool.
- **Benchmark:** the return from the first orchestrator snapshot's date to today,
  compared with the orchestrator's total return over the same period. Because the
  window starts at that first snapshot, its value is the base:
  `excess = value/first_value - 1 - benchmark_return`.
  This keeps it a like-for-like window even when the orchestrator was deployed earlier
  than its first snapshot.
- **Best and worst bot:** active orchestrator bots that have a snapshot today, ranked
  by `bot_daily_pnl`. Both lines show when there are at least two bots; a single bot
  shows "Only bot: …"; no active bots omits the line.
- **Started / Stopped:** read from the orchestrator's bots, not from the run's applied
  actions, so the push reflects what actually happened:
  - **Started:** bots with `created_at` on the job's America/New_York date.
  - **Stopped:** bots with `stopped_at` on that date, labelled by `stop_reason`
    (`orchestrator` → "orchestrator", `drawdown_kill_switch` → "kill-switch").
    This covers kill-switch stops, which no decision run records.
  - Each entry shows the preset display name (falling back to the strategy name) and
    tickers. Started bots also show capital; stopped bots show their return on allocated
    capital (`bot_value / initial_capital - 1`, which is final once the bot is flat).
  - Each list is capped at 5 entries plus "+N more". Pushover's message limit is 1,024
    characters, and the bot push already uses about 400.
- **Decision run:** the status of the newest run created on that date, failed runs with
  their error truncated to 80 characters. No run shows "No decision run today".
- Formatting helpers (`_signed_money`, `_signed_pct`) are imported from
  `strategy_bots.notifications` so the pushes read the same.

**5. Settle before snapshotting.** `settle_returned_capital` runs per orchestrator first,
so a bot sold flat during the day has already moved its cash into free capital.

## Risks / Trade-offs

- [A bot that is stopped but still selling is no longer active, so it drops out of
  best/worst on the day it stops] → acceptable; the push's value already includes it
  (its value counts until its cash is returned).
- [Users relying on the per-bot pushes of orchestrator bots lose them] → this is what
  the user chose (roll-up); the bot detail page still has every figure.
- [The stale `add-strategy-bot-notifications` change still holds older copies of two
  requirements] → this change adds only a new requirement and modifies none of those, so
  it does not conflict. The stale change should later be archived without re-syncing its
  outdated blocks.

## Migration Plan

One Alembic revision creates `bot_orchestrator_snapshots` with its unique constraint. The
backend applies it on container start; deploy with `docker compose up -d --build`.
Rollback drops the table; the push logic simply stops finding snapshots.
