## Why

Everything needed to learn from a day's AI trading decision already exists, but it is scattered across three unjoined places: the rebalance's `AIPortfolioEvent` (reasoning in `result_payload`, indicator values in `trend_context`, order/fill/realized-P&L detail in `run_stats`), the per-day `SessionValueSnapshot` (daily P&L, keyed only by session+date), and the reconciled `PaperTrade` rows (authoritative filled prices, known only after reconciliation). There is no single per-portfolio, per-day record that ties the decision, the signals it saw, the orders it actually filled, and that day's P&L outcome together — which is exactly the shape offline learning needs.

## What Changes

- Add a new **backend-only** `session_daily_run_snapshots` table holding one consolidated row per session (portfolio) per calendar day, assembled from already-persisted data — no re-computation of indicators and no re-running of the agent.
- Each row consolidates: the day's rebalance event reference + AI reasoning (`result_payload`), the technical-indicator values used (`trend_context`), the filled orders including reconciled filled price (from `run_stats.trades` / `PaperTrade`), the run outcome stats (orders/realized P&L/account/gate/guardrails), and that day's P&L/valuation (from `SessionValueSnapshot`).
- Add a new **dedicated cron-guarded endpoint + service** that assembles these rows for the day's selected sessions. It runs **after** the existing end-of-day P&L snapshot job, so order fills are reconciled and the value snapshot exists before assembly. Idempotent per session per day; best-effort per session (one failure does not abort the batch).
- **No** read schema, API read, or frontend surface — this mirrors the deliberate decision to keep `run_stats` out of `AIPortfolioEventRead`. The data is for export/learning only.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ai-paper-trading`: adds a requirement for a consolidated per-session, per-day learning snapshot and the dedicated post-P&L assembly job that produces it.

## Impact

- **New table + migration:** `session_daily_run_snapshots` (Alembic migration, `down_revision` = current head).
- **New endpoint:** a cron-token-guarded `POST` under `/api/v1/ai-portfolio/...` that triggers assembly; sequenced in deployment (cron) to run after `snapshot-daily`.
- **New service logic** in `ai_portfolio/service.py` (assembly), reading existing `AIPortfolioEvent`, `SessionValueSnapshot`, and `PaperTrade` data.
- **Reuses** existing data only (`run_stats`, `trend_context`, `result_payload`, `SessionValueSnapshot`, reconciled `PaperTrade`); does not change the rebalance run, the existing snapshot job, or indicator computation.
- **No frontend change.** No change to existing read schemas/APIs.
- Deployment: one new cron entry ordered after the P&L snapshot cron (a scheduling concern, not enforced by the endpoint).
