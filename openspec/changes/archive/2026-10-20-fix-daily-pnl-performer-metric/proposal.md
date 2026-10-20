## Why

The daily P&L Pushover notification's "Best/Worst" performer line reports each
holding's **since-entry** return (`current price ÷ weighted-average cost − 1`),
not the day's price move. Because two sessions can hold the same ticker at a
different average cost, the same live quote yields different — even
opposite-sign — figures: on 2026-10-17 MSFT showed as the *worst* performer at
−1.09% in one session and the *best* at +2.08% in another, on the same day.
Worse, the line sits in a message whose header (`daily_pnl` / `daily_pnl_pct`)
*is* a true daily figure, so one push mixes a daily portfolio number with a
since-entry per-asset number and labels the latter a daily "performer".

## What Changes

- The daily P&L push's Best/Worst performer line now reports each held asset's
  **true day-over-day price change** = `today_price / prior_snapshot_price − 1`,
  so the same ticker shows the **same** percentage in every session's push on a
  given day and is consistent with the message's daily header.
- Today's per-asset price comes from the snapshot just recorded for the current
  run; the prior day's per-asset price comes from the session's most recent
  earlier value snapshot (the "previous available snapshot", not literally
  yesterday — markets close on weekends/holidays). The per-asset `price` is
  already persisted in each `SessionValueSnapshot.positions` entry, so no new
  storage is needed.
- Edge-case handling for the performer line (materially affects what the push
  shows — flagged for review):
  - **No prior snapshot** (a session's first daily report): the line is
    **omitted** for that push (no daily change is computable for any asset).
  - **A holding absent from the prior snapshot** (opened/first appeared today):
    that single asset is **excluded** from the Best/Worst candidate set for the
    day (no fabricated figure from avg-cost); other assets are still compared.
  - **Prior price missing or ≤ 0** for a ticker: that ticker is **excluded**.
  - If **no** assets remain comparable after exclusions, the line is **omitted**.
- The snapshot document's per-position `return_pct` (since-entry) is **unchanged**
  and continues to serve every other consumer; only the notification's performer
  line stops reading it.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ai-paper-trading`: the daily P&L notification requirement changes so the
  per-asset Best/Worst performer line reports a true daily price change (with the
  documented exclusion/omission rules) instead of a since-entry return.

## Impact

- `backend/src/cadence/ai_portfolio/snapshots.py` — `snapshot_all_sessions`
  builds the notification's `holdings` list from the computed daily change
  (today vs. previous snapshot) rather than from each position's `return_pct`.
- `backend/src/cadence/paper_trading/service.py` — expose a public accessor for
  the session's previous value snapshot (a thin wrapper over the existing
  private `_prior_snapshot`, which already backs the header's daily P&L), for
  use and unit-testing by the snapshot job.
- `backend/src/cadence/ai_portfolio/notifications.py` — no behavior change:
  `_best_worst_line` keeps its max=Best / min=Worst / `_signed_pct` formatting
  and simply receives true-daily values.
- No migration, no schema change, no API change, no frontend change. Snapshot
  and push scheduling, weekend crypto gating, and the daily-run learning
  snapshot are all unchanged.
