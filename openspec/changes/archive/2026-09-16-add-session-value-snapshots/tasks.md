> Prerequisite: apply `add-session-position-ledger` first. This change reads the
> session position ledger for holdings and cost basis, and its migration chains after
> the ledger migration.

## 1. Schema: session_value_snapshots table

- [x] 1.1 Add a `SessionValueSnapshot` ORM model to `paper_trading/models.py` (UUID PK, `session_id` FK → `paper_trading_sessions.id` `ON DELETE CASCADE`, `snapshot_date` Date, `total_value`/`cash_value`/`positions_value`/`daily_pnl`/`daily_pnl_pct` Float, `positions` JSONB, `created_at` timestamp) with `UniqueConstraint(session_id, snapshot_date)` and an index on `(session_id, snapshot_date)`. Verify by importing the model and `Base.metadata` lists the table.
- [x] 1.2 Add an Alembic migration (`down_revision` = the `add-session-position-ledger` migration head) creating the table + unique constraint; `downgrade` drops it. Verify with `uv run alembic upgrade head` then `downgrade base` then `upgrade head`, and `uv run alembic check` reports no drift.

## 2. Backend: valuation + snapshot persistence

- [x] 2.1 In `paper_trading/service.py` add `compute_session_value(session, *, session_id, broker)` returning total/cash/positions value + per-position breakdown, computed as `allocated_capital + realized total_pnl + Σ(market_value − cost_basis)` over the session's ledger positions (`list_open_positions`; `market_value` from `broker.get_quotes`; a position whose quote fails is valued at its ledger avg cost and logged). Verify with unit tests: all-cash session (empty ledger), session with a marked-up and marked-down ledger holding, and a quote-failure isolated to one ticker.
- [x] 2.2 Add `record_value_snapshot(session, *, session_id, as_of, ...)` that reads the existing `(session_id, snapshot_date)` row and updates it, else inserts; computes `daily_pnl` vs the prior snapshot's `total_value` or `allocated_capital`, and `daily_pnl_pct` (guarded on `baseline > 0`). Verify with a test that two runs on the same `as_of` yield exactly one row (idempotent) and that `daily_pnl` uses the prior snapshot on the second day.
- [x] 2.3 Add `list_value_snapshots(session, *, session_id)` returning snapshots ordered oldest-first. Verify with a service test asserting ascending `snapshot_date`.

## 3. Backend: daily orchestration + Pushover report

- [x] 3.1 In `ai_portfolio/service.py` add `snapshot_all_sessions(session, *, broker, notifier, as_of=None)` that lists active sessions, filters to `strategy_key == AI_STRATEGY_KEY`, records a snapshot per session, builds the report (per-session value + P&L line; best/worst held position by `return_pct` across all sessions, omitted when there are no holdings), and sends it via the safe-notify wrapper. Verify with a service test asserting only active AI sessions are snapshotted and the sent message contains the per-session lines + best/worst holding.
- [x] 3.2 Verify notifier isolation: a test where `notifier.send` raises confirms the job still completes and snapshots persist.

## 4. Backend: endpoints + schemas

- [x] 4.1 Add response schemas to `api/schemas.py`: `SessionValueSnapshotRead`, `SessionValueHistoryResponse` (items + total), and `AIDailySnapshotResponse` (sessions_snapshotted + ids). Verify they `model_validate` a snapshot ORM row in a test.
- [x] 4.2 Add `POST /ai-portfolio/snapshot-daily` to `api/routers/ai_portfolio.py`, guarded by `require_valid_cron_token`, calling `snapshot_all_sessions` and returning `AIDailySnapshotResponse`. Verify with API tests: 403 on missing/invalid token; a valid-token run snapshots active AI sessions and returns the count.
- [x] 4.3 Add `GET /paper-trading/sessions/{id}/value-history` to `api/routers/paper_trading.py` returning `SessionValueHistoryResponse` oldest-first. Verify with an API test asserting ascending order and the snapshot fields.

## 5. Ops: schedule the cron

- [x] 5.1 Add a `SNAPSHOT_SCHEDULE` env (default `15 16 * * 1-5`) and a second generated script + crontab line to the `cron` service in `docker-compose.yml` that curls `POST /api/v1/ai-portfolio/snapshot-daily` with `-H X-Cron-Token:$T`; document `SNAPSHOT_SCHEDULE` in `.env.example`. Verify by rendering the compose config (`docker compose config`) and confirming both cron lines are present.

## 6. Frontend: value history chart

- [x] 6.1 Add `SessionValueSnapshot` + `SessionValueHistoryResponse` to `types/api.ts`, and a `valueHistory` query key + `listSessionValueHistory` fetcher + `useSessionValueHistory` hook to `api/paperTrading.ts`. Verify with `npm run typecheck`.
- [x] 6.2 Add `pages/paper-trading/SessionValueChart.tsx`: a dependency-free inline-SVG line chart of `total_value` over time (mirroring `PriceSparkline`), wrapped in the page's `Panel` with loading/error states and a "not enough history" placeholder when fewer than 2 points; render it on `PaperTradingSessionPage.tsx` after `SessionHeader`. Verify by viewing the session page.
- [x] 6.3 Add co-located tests (`SessionValueChart.test.tsx` and/or extend `PaperTradingSessionPage.test.tsx`) covering: chart renders a polyline with ≥2 snapshots, the placeholder with <2, and the loading/error states. Verify with `npx vitest run`.

## 7. Verification

- [x] 7.1 Backend: `uv run ruff check .`, `uv run mypy src/cadence`, `uv run pytest` all pass; Alembic round-trip + `alembic check` clean.
- [x] 7.2 Frontend: `npm run typecheck`, `npx vitest run`, `npm run build` all pass.
- [x] 7.3 `openspec validate add-session-value-snapshots --strict` passes.
