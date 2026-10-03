## Why

The end-of-day value snapshot and per-session P&L report currently run on weekdays
only: the cron sidecar schedules `SNAPSHOT_SCHEDULE` as `15 16 * * 1-5` (Mon–Fri).
But sessions now rebalance their crypto sleeve on weekends (the weekend crypto-only
trigger, `35 9 * * 6,0`), and crypto trades around the clock, so a session's value
and P&L genuinely move on Saturdays and Sundays. With no weekend snapshot, those days
produce no value-history point and no P&L push, leaving a gap in the recorded NAV
series and no weekend report. We want the daily P&L report (and its value snapshot) to
run every day, including weekends.

## What Changes

- The end-of-day snapshot + daily P&L report SHALL run on **every calendar day,
  including weekends**, not only weekdays. The default snapshot cron schedule changes
  from `15 16 * * 1-5` to `15 16 * * *` (16:15 ET, all 7 days).
- No backend logic change is required: the snapshot endpoint/service
  (`/ai-portfolio/snapshot-daily` → `snapshot_all_sessions`) is already day-agnostic
  — it has no market-open guard and no weekday assumption, records one idempotent
  snapshot per active AI session, marks positions (including crypto) to market, and
  sends one P&L push per session. This change schedules it to fire on weekends too.
- Deployment docs (`.env.example`, `README.md`) are updated to document the all-days
  default for `SNAPSHOT_SCHEDULE`.
- Behaviour that is explicitly unchanged: the snapshot/report content and per-session
  message, idempotency per session per calendar day, the cron-token guard, the
  weekday equity rebalance and weekend crypto rebalance triggers, and the fact that
  report-delivery failures never fail the snapshot job.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `ai-paper-trading`: the "Snapshot session portfolio value at end of day" requirement
  is clarified to state the end-of-day snapshot and P&L report are intended to run on
  every calendar day (including weekends), so a session's value and P&L are recorded
  and reported on weekends when its crypto sleeve has moved. The scheduling cadence
  itself remains a deployment concern (the cron schedule); the endpoint already
  operates on any day it is validly called.

## Impact

- **Deployment — cron sidecar:** `docker-compose.yml` default for `SNAPSHOT_SCHEDULE`
  changes from `15 16 * * 1-5` to `15 16 * * *`. Operators who pin `SNAPSHOT_SCHEDULE`
  in their `.env` keep their value; only the built-in default changes.
- **Docs:** `.env.example` and `README.md` updated to reflect the all-days default and
  explain weekend P&L reporting (mirroring the existing weekend crypto-rebalance note).
- **No backend code change, no schema/migration, no API change, no frontend change.**
  `snapshot_all_sessions` / the `/ai-portfolio/snapshot-daily` endpoint already work on
  any calendar day; they are unchanged.
- **Unaffected:** the weekday equity rebalance trigger, the weekend crypto-only
  rebalance trigger, benchmark fetch, technical-indicator runs, and the snapshot's
  content, idempotency, and cron-token guard.
