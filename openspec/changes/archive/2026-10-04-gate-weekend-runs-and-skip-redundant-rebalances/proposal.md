## Why

Weekend behavior currently keys off what a session *holds* (`session_involves_crypto`) rather than the scope the user *configured* (`asset_types`). A stocks-only session that happens to hold or target a crypto asset therefore gets weekend crypto rebalances and weekend daily-P&L Pushover notifications it should never receive — the user reports weekend notifications for portfolios that are not supposed to use crypto. Separately, rebalance runs still execute when they cannot do anything meaningful (most visibly the first rebalance right after a build, where the cash is already deployed), churning transaction fees and sending noise notifications.

## What Changes

- Make a session's **configured** asset scope the single source of truth for weekend behavior:
  - Add a `session_allows_crypto(session_row) -> bool` helper that reads `asset_types` from `session_metadata` (default `both`) and returns `True` only when the configured scope includes crypto (scope is `crypto` or `both`).
  - **Weekend crypto rebalance** (`rebalance_crypto_daily`) selects sessions by configured scope (`session_allows_crypto`) instead of holdings (`session_involves_crypto`); stocks-only sessions are bucketed as skipped and never rebalanced on weekends.
  - **Weekend daily-P&L** (`snapshot_all_sessions`): on Saturday/Sunday, a stocks-only session is skipped entirely — **no value snapshot recorded and no notification sent**. Crypto/`both`-scoped sessions still snapshot + notify on weekends. **Weekdays are unchanged** (all active AI sessions snapshot + notify).
  - "Weekend" is determined by calendar (Saturday/Sunday in the snapshot market-close timezone `_SNAPSHOT_TZ`), ignoring market holidays — consistent with the existing `weekday() < 5` approximation.
- Skip redundant rebalance runs (applies to **all** rebalance runs — weekday full rebalance and weekend crypto-only):
  - After the executor plans the trade intents (sells then buys, before any order is submitted), if the plan has **zero sell intents** and there is **no deployable unallocated cash** to fund the planned buys, skip the run: submit nothing, record it as a no-op/skipped run, and send no rebalance notification.
  - "No deployable unallocated cash" means no free session cash beyond the reserved cash buffer — not enough to fund any planned buy. Consequence: the first rebalance immediately after a build always skips. A run with deployable cash + buy-only still runs (deploys the cash); a run with at least one sell still runs (reallocates).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ai-paper-trading`: weekend crypto rebalance selection and weekend daily-P&L snapshot/notification gate on configured scope rather than holdings; rebalance runs are skipped when the plan is buy-only with no deployable cash.

## Impact

- `backend/src/cadence/ai_portfolio/service.py`: new `session_allows_crypto` helper; `snapshot_all_sessions` weekend scope gating + calendar weekend check; rebalance orchestration records a skipped run when the plan is buy-only with no deployable cash.
- `backend/src/cadence/ai_portfolio/executor.py`: `execute_rebalance` decides the buy-only/no-deployable-cash skip from the planned intents before submitting any order.
- `backend/src/cadence/api/routers/ai_portfolio.py`: `rebalance_crypto_daily` selects sessions via `session_allows_crypto`; new/renamed skip bucket for non-crypto-scoped sessions.
- No database migration (scope already lives in `session_metadata` JSONB; no new columns).
- Tests: `backend/tests/` covering the scope helper, weekend rebalance/snapshot gating, weekday-unchanged behavior, the buy-only skip (including first-run-after-build), and Saturday/Sunday calendar detection.
