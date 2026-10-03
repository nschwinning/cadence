## Context

See `proposal.md` — Why. Current state of the relevant seams (verified against the code):

- **The snapshot endpoint/service is already day-agnostic.** `snapshot_all_sessions`
  (`ai_portfolio/service.py`) has **no market-open guard and no weekday assumption**:
  it defaults `as_of` to `datetime.now(tz=_SNAPSHOT_TZ).date()`, fans over every active
  AI session, calls `record_value_snapshot` (idempotent per session per calendar day),
  and sends one P&L push per session via `_notify_safely`. The `/ai-portfolio/snapshot-daily`
  router simply calls it. Nothing in that path cares whether the day is a weekday.
- **The only thing gating weekends is the cron schedule.** The cron sidecar in
  `docker-compose.yml` writes `/etc/crontabs/root` from env schedules. `SNAPSHOT_SCHEDULE`
  defaults to `15 16 * * 1-5` (Mon–Fri at 16:15 ET), so the endpoint is simply never
  POSTed on Saturdays or Sundays.
- **Weekend crypto rebalances already run.** `CRYPTO_REBALANCE_SCHEDULE` (`35 9 * * 6,0`)
  rebalances the crypto sleeve on weekends and records runs + sends Pushover. So weekend
  activity exists; only the weekend EOD snapshot/report is missing.
- **Precedent for "cadence is a deployment concern."** The daily-rebalancing spec's
  "Cron-guarded weekend crypto-only rebalance trigger" states the scheduling cadence is
  a deployment concern, not enforced by the endpoint. The snapshot requirement follows
  the same shape: the endpoint operates on any valid call; the schedule decides the days.

## Goals / Non-Goals

**Goals:**
- Have the end-of-day value snapshot and per-session P&L report fire on weekends too,
  so weekend crypto moves are captured in the NAV series and reported.
- Keep the change to its minimal surface: a cron-schedule default plus docs, with the
  spec clarified to state all-days operation.

**Non-Goals:**
- No backend code change: the snapshot service/endpoint already works any day.
- No new endpoint (unlike the weekend crypto trigger, which needed a distinct
  crypto-only endpoint — here the one existing snapshot endpoint already does the right
  thing on any day).
- No schema/migration, no API change, no frontend change.
- No change to snapshot content, idempotency, the cron-token guard, or the rebalance
  triggers.

## Decisions

**1. Extend the existing snapshot schedule to all 7 days rather than add a separate
weekend endpoint.**
Change the default `SNAPSHOT_SCHEDULE` from `15 16 * * 1-5` to `15 16 * * *`. The
endpoint is already day-agnostic and idempotent per calendar day, so a single all-days
schedule is correct and simplest.
- *Why over a separate weekend snapshot endpoint (mirroring the weekend crypto
  trigger):* the crypto trigger needed its own endpoint because it does something
  **different** on weekends (crypto-only scope, skipping equities). The snapshot does
  the **same** thing every day — mark holdings to market and report — so a second
  endpoint would be duplicate wiring with no behavioural difference. One schedule, all
  days, is the right tool.
- *Why keep 16:15 ET on weekends:* consistency with the weekday EOD time keeps one
  snapshot-per-day cadence; equity prices are stale (Friday close) but crypto is live,
  which is exactly the weekend value we want to capture.

**2. Only the built-in default changes; operator overrides are preserved.**
`docker-compose.yml` uses `${SNAPSHOT_SCHEDULE:-...}`; an operator who sets
`SNAPSHOT_SCHEDULE` in their `.env` is unaffected. `.env.example` and `README.md` are
updated so the documented default and the compose default agree.

## Risks / Trade-offs

- **Weekend snapshots record stale equity prices (Friday close) alongside live crypto
  marks** → Accepted: this is correct — equities genuinely did not move, crypto did, and
  the P&L baseline (prior snapshot / allocated capital) makes the weekend day's P&L
  reflect the crypto move. The NAV series gains Saturday/Sunday points that were
  previously missing.
- **An operator pinning the old weekday-only schedule keeps weekday-only behaviour** →
  Accepted and documented; the change only moves the default.
- **Two extra P&L pushes per weekend** → intended (the user asked for weekend P&L
  reports); report delivery is best-effort and never fails the job.

## Migration Plan

No data migration. The change is a cron-schedule default plus docs. Rollback is
reverting the `SNAPSHOT_SCHEDULE` default. Deployments that already pin the variable
are unaffected; deployments relying on the default begin receiving weekend snapshots
and reports after redeploy.
