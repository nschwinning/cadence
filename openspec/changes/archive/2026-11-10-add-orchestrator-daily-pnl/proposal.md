## Why

AI portfolios and strategy bots each send an evening daily-P&L push, but a bot
orchestrator sends none, and the bots it deploys each send their own push with an
unlabelled strategy-plus-tickers title. An orchestrator running three bots therefore
produces three loosely related pushes and no answer to "how did the orchestrator do
today?". The user wants one daily P&L push per orchestrator that covers its bots.

## What Changes

- **Daily orchestrator value snapshot.** The evening bot snapshot job (16:15 ET on
  weekdays), right after snapshotting the bots, records one snapshot per active
  orchestrator: date, value, free capital, allocated capital and active bots. These
  give the day-over-day baseline the push needs, and the history an orchestrator value
  chart could use later.
- **Orchestrator daily P&L push.** One push per active orchestrator, titled
  `Cadence orchestrator: <label> daily P&L`, carrying:
  - value with day change (amount and %), against the previous snapshot or, on the
    first day, the capital pool;
  - total return on the capital pool;
  - free and allocated capital, and active bots out of the maximum;
  - a benchmark comparison since the first snapshot, when closes are available;
  - the best and worst bot by today's P&L;
  - the bots **started** today (preset, tickers, capital) and the bots **stopped**
    today (preset, tickers, reason — orchestrator decision or drawdown kill-switch —
    and return), each list capped at five;
  - the status of that morning's decision run, or that there was no run today.
- **Roll-up of bot pushes.** Bots deployed by an orchestrator are still snapshotted,
  but **no longer send their own daily push**; the orchestrator's push covers them.
  Manually created bots keep their per-bot push unchanged.
- **Spec catch-up.** The per-bot daily push was introduced by the unarchived
  `add-strategy-bot-notifications` change and never reached the main spec. This change
  adds that requirement to `strategy-bots`, documenting the existing push plus the new
  orchestrator exclusion.
- **Migration:** one new table, `bot_orchestrator_snapshots`, unique per orchestrator
  and day.

## Capabilities

### New Capabilities

<!-- None. -->

### Modified Capabilities

- `bot-orchestrator`:
  - adds an "Orchestrator daily snapshots" requirement;
  - "Orchestrator notifications" gains the daily P&L push.
- `strategy-bots`: adds a "Bot daily summary notification" requirement (the existing
  per-bot push, excluding orchestrator-deployed bots).

## Impact

- **Backend**:
  - new `bot_orchestrator/daily.py` (snapshot, message, push);
  - `bot_orchestrator/models.py` (`BotOrchestratorSnapshot`);
  - `strategy_bots/service.py`: skip the push for orchestrator bots; a public
    `bot_daily_pnl` helper;
  - `api/routers/bots.py` (`/bots/snapshot-daily` composes the orchestrator step) and
    its response schema;
  - one Alembic migration (applied on container start).
- **No frontend change** and no cron change: the step rides the existing 16:15 bot
  snapshot job.
- **Unchanged**: AI-portfolio pushes, manual-bot pushes, kill-switch pushes, the
  orchestrator decision-run pushes.
- **Out of scope**:
  - an orchestrator value chart (now possible from the snapshots);
  - reconciling and archiving the stale `add-strategy-bot-notifications` change.
