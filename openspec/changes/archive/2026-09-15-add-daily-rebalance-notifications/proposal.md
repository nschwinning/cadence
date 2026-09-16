# Push notifications for daily rebalance orders

## Why

The daily rebalance runs unattended on a cron trigger. When it submits orders the
operator has no signal it happened without opening the app, and — worse for an
unattended job — a failed daily run is silent (only logged server-side). The
sibling `trading-bot` app already sends Pushover notifications after a run places
trades; Cadence should do the same for its daily rebalance, adapted to Cadence's
conventions (settings-based config + an injectable Protocol, not `os.getenv`).

## What Changes

- **New `notify` capability (Pushover).** Add a `Notifier` protocol with a real
  `PushoverNotifier` (posts to the Pushover messages API via `requests`, reading
  `PUSHOVER_USER`/`PUSHOVER_TOKEN` from `settings`) and a no-op `NullNotifier`, plus
  a `get_notifier()` DI factory — mirroring the `broker` package. When credentials
  are absent the notifier is a silent no-op so the app still boots and runs.
- **Notify on daily rebalance outcomes.** The daily (cron) rebalance sends a push
  when it **submits one or more orders** (summarizing portfolio, order count, and
  each order's side + ticker) and when a daily run **fails** (with a brief reason).
  It does NOT push for market-closed/zero-order skips.
- **Daily-only, best-effort.** Manually-triggered rebalances do NOT notify: the
  daily endpoint injects a `Notifier` down the job path while the manual endpoint
  passes none, so `run_rebalance_event` notifies only when a notifier is present.
  Sending is wrapped so a notification failure is logged and never affects the
  rebalance or its recorded event.
- **Config + env.** Add `PUSHOVER_USER` and `PUSHOVER_TOKEN` to `Settings` and
  document them in `.env.example` (both optional; empty disables notifications).

## Impact

- Affected specs: `daily-rebalancing` — ADDED "Notify on daily rebalance outcomes".
- Affected code (new): `cadence/notify/` package (`base.py` protocol + errors,
  `pushover.py`, `null.py`, `__init__.py` with `get_notifier`).
- Affected code (modified): `config.py` (+2 settings); `ai_portfolio/background.py`
  (`start_rebalance`/`_job_rebalance` thread an optional `Notifier`);
  `ai_portfolio/service.py` (`run_rebalance_event` gains an optional `notifier`;
  sends on the executed-orders success path and in the failure handler);
  `api/routers/ai_portfolio.py` (daily endpoint injects `get_notifier`; manual does
  not); root `.env.example`.
- Tests: new `notify` unit tests (Pushover payload/creds-missing/transport-error,
  null no-op); service tests that the daily path notifies on executed orders and on
  failure, stays silent on skip/zero-orders and for manual rebalances, and that a
  notifier error does not fail the rebalance.
- No database/schema/migration change. Order routing and market-open behavior are
  unchanged.
