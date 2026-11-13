## Why

Strategy-bot orders that fill after the bot engine stops waiting are left in the order journal for
reconciliation, but reconciliation only runs at the start of a bot tick — and the tick returns
immediately once the market is closed. An order sent in the last minutes of the session (for
example 15:55 ET) therefore stays unbooked overnight: the Admin page shows an orphan broker
position plus an unresolved order, and that evening's daily value snapshot omits the position
while still counting the cash as unspent. It is only repaired at the next session's first tick
(or by a manual "Reconcile now").

## What Changes

- The daily strategy-bot snapshot job (cron, 16:15 ET on weekdays) reconciles unbooked
  **bot-owned** journal records before it records any snapshot, so late fills are booked the same
  evening and the snapshot reflects them.
- Reconciliation failures never block the snapshots (per-record isolation already applies; an
  unexpected error in the pass is logged and the snapshots still run).
- The snapshot job's response reports how many records were booked (`reconciled`), as the tick
  response already does.
- No migration, no new setting, no frontend change.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `order-journal`: reconciliation also runs before the daily strategy-bot value snapshot.

## Impact

- Backend: `strategy_bots/service.py` (`run_bot_snapshots` reconciles first and returns the
  count), `api/routers/bots.py` + `api/schemas.py` (`BotSnapshotResponse.reconciled`).
- Tests: snapshot-job tests for a late fill booked before the snapshot and a reconciliation
  failure not blocking snapshots.
