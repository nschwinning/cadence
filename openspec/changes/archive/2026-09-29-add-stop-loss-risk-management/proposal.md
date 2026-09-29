## Why

AI-managed paper-trading sessions currently have no automatic downside protection: a
position can fall arbitrarily far between the once-daily rebalances, and the only
"exit" signals are soft (the AI's judgement, optionally nudged by trend reversal
flags). Users want a deterministic, opt-in floor that cuts a losing position without
waiting for the next daily rebalance — a hard stop-loss — while leaving existing
sessions untouched.

## What Changes

- Add an **opt-in hard stop-loss**, chosen at build time and **frozen** on the
  session (default **off**; all existing sessions treated as off). When on, a held
  position is fully sold once its live price falls to or below
  `avg_cost × (1 − stop_loss_pct)`, where `avg_cost` is the session ledger's
  weighted-average cost.
- Add a per-session **stop-loss threshold** (`stop_loss_pct`), selectable on the
  build form, frozen on the session, with a configured global default.
- Add a **new dedicated cron trigger** (shared-secret guarded, like the other cron
  endpoints) that scans the open positions of **all active opted-in sessions** and
  is intended to run more frequently than the daily rebalance. It dedups tickers
  across sessions and fetches quotes in **batched multi-symbol** requests to respect
  Alpaca rate limits. Equity sells are guarded by market status (only when the
  market is open); crypto sells run around the clock.
- Record each stop-out through the existing execution/recording path: a trade with a
  **stop-loss signal type** and no AI-portfolio-event reference, a session run with a
  **stop-loss trigger**, a closed position with realized P&L, the per-trade
  transaction cost, and a best-effort push notification per stop-out.
- Add a **cooldown quarantine**: each stopped ticker is recorded per session with an
  "excluded-until" date (default cooldown a configured number of trading days). The
  daily-rebalance candidate assembly **excludes quarantined tickers** for the
  cooldown window so the AI cannot immediately re-buy a just-stopped position.
- Add a **batched multi-symbol quote** capability to the brokerage abstraction so a
  single scan is a few requests rather than one-per-symbol.
- Surface the stop-loss settings **read-only** on the session read model; add a
  **default-off toggle + threshold input** on the AI build form; show the stop-loss
  configuration on the **session detail** view; and make **stop-loss runs visible**
  in the Runs history/detail.
- **Out of scope (v2):** a separate crypto-specific threshold (a single threshold
  applies to both equities and crypto for now); trailing stops, take-profit, and
  portfolio-level drawdown breakers (explored but deferred); broker-native stop
  orders. Note: on the free-tier Alpaca data feed, equity quotes are IEX-only
  real-time — a known accuracy limitation of equity stops, not a code dependency.

## Capabilities

### New Capabilities
<!-- None. The stop-loss behavior extends the existing ai-paper-trading capability
     rather than introducing a new capability directory. -->

### Modified Capabilities

- `ai-paper-trading`: the build requirement gains the frozen stop-loss opt-in +
  threshold; a new requirement covers the dedicated stop-loss scan/evaluation, its
  execution and recording, and the cooldown-quarantine state; the brokerage
  abstraction gains batched multi-symbol quotes; the session read model exposes the
  stop-loss settings.
- `daily-rebalancing`: the rebalance requirement's candidate assembly excludes a
  session's quarantined (recently stopped) tickers for the cooldown window.
- `app-shell`: the AI build form gains the stop-loss toggle + threshold input, the
  session detail view shows the stop-loss configuration, and stop-loss runs appear
  in the Runs history/detail views.

## Impact

- **Backend:** `paper_trading` models (new frozen `stop_loss_enabled` +
  `stop_loss_pct` columns; new per-session stop-quarantine state) + Alembic
  migration (non-nullable columns backfilled off; new quarantine table); `broker`
  abstraction + Alpaca impl (batched `get_quotes`); `ai_portfolio` service (stop-loss
  scan/evaluation, execution + recording reuse, quarantine writes) and rebalance
  candidate assembly (quarantine exclusion); a new cron-guarded router endpoint;
  `api/schemas.py` (`AIPortfolioBuildRequest` + `PaperTradingSessionRead`); settings
  (default threshold, cooldown length); notifications (stop-out push).
- **Frontend:** `types/api.ts`, the AI build form, the session detail view, and the
  Runs views.
- **Ops:** a new scheduled trigger must be registered to call the stop-loss cron
  endpoint at the desired frequency (guarded by the existing cron-token secret).
- **Data feed:** relies on the existing Alpaca latest-quote source; equity stop
  precision is bounded by the account's Alpaca market-data plan.
