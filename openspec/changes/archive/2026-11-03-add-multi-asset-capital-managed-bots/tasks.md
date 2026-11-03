## 1. Data model & migration

- [x] 1.1 In `strategy_bots/models.py`, add a `BotPosition` ORM model (session FK, asset FK + frozen ticker, qty, avg entry price, opened-at; unique on (session, asset)) and a session→positions relationship; verify `uv run mypy src/cadence` passes and a model-level unit test instantiates a session with multiple positions.
- [x] 1.2 In `strategy_bots/models.py`, replace the session's single `asset_id`/`ticker`/inline-position columns with a traded-symbol-set relationship and add `cash`, `sizing_method`, `risk_pct`, `atr_period`, `atr_k`, `max_position_pct`, `max_positions` columns (keep existing `cash_buffer_pct`, TP/SL, drawdown fields); verify the module imports and mypy passes.
- [x] 1.3 Add an Alembic migration creating `bot_positions` + the symbol-set table, adding the new session columns, dropping the old single-asset/inline-position columns, and backfilling existing sessions to the N=1 shape (`sizing_method='all_in'`, `max_positions=1`, `max_position_pct=1.0`, one symbol row, one open position row if applicable, `cash` set from capital/holdings); verify `alembic upgrade head` then `downgrade -1` runs clean against a scratch DB.

## 2. Sizing & capital-pool core (pure, unit-tested)

- [x] 2.1 Add a pure `atr(bars, period)` helper (Wilder True Range mean) in `strategy_bots/`; verify a unit test against hand-computed ATR for a small fixed bar series, including the insufficient-history / zero-ATR cases returning "unavailable".
- [x] 2.2 Add a pure `size_position(...)` helper implementing ATR risk-based and all-in methods bounded by per-name cap, cash buffer, and remaining cash, flooring to whole shares and returning 0 below one share; verify unit tests cover: equal-dollar-risk (higher ATR → fewer shares), per-name cap binding, cash binding, and the <1-share skip.
- [x] 2.3 Add a pure shared-pool allocation step that, given candidate entries in deterministic (ascending-ticker) order, funds entries only while they fit remaining cash and the max-concurrent-positions limit; verify a unit test proves Σ open-position cost never exceeds the budget when more symbols signal than cash/slots allow.

## 3. Multi-asset session service

- [x] 3.1 In `strategy_bots/service.py`, implement multi-asset `create_bot_session` accepting a symbol set or a whole-universe selection (resolving the eligible universe at creation), validating every symbol is an eligible universe stock and rejecting unknown strategies / non-universe assets; verify unit tests for create-with-set, create-whole-universe, and rejection paths.
- [x] 3.2 Rework the tick runner for multi-asset sessions: per session fetch each symbol's bars (reusing the IEX freshness/skip-on-stale path), recompute indicators, process **exits before entries** (drawdown kill-switch → per-position TP/SL → EXIT signal), then deterministic-order entries via the §2 allocation step; keep it stateless. Verify unit tests with a stubbed broker/market-data for: exits-before-entries ordering, max-positions enforcement, budget ceiling, per-position TP/SL, whole-session drawdown stop, and per-symbol stale-data skip.
- [x] 3.3 Generalize value snapshots and KPIs to `cash + Σ marked positions` with aggregated realised/unrealised P&L; verify unit tests for a multi-position snapshot and KPI computation.
- [x] 3.4 Update the dashboard performance adapter to compute current value as cash + all marked positions while keeping the existing per-session shape (`kind='bot'`, value series, contributions, since-inception benchmark); verify the adapter test still returns the shared shape for a multi-position bot.
- [x] 3.5 Add a strategy `explanation` field to the registry/catalog and expose it via the strategy catalog endpoint; verify a unit test asserts the catalog response includes the MA-Crossover explanation.

## 4. API & schemas

- [x] 4.1 Update `api/schemas.py` and the `/api/v1/bots` router: create request accepts a symbol set / whole-universe flag + sizing params (`sizing_method`, `risk_pct`, `atr_period`, `atr_k`, `max_position_pct`, `max_positions`); session/KPI responses expose multiple positions; catalog exposes `explanation`. Verify router tests for create (set + whole-universe), validation errors mapped to HTTP status, and the positions/catalog payloads.

## 5. Frontend — picker, detail, strategy page, create→nav

- [x] 5.1 Build a reusable universe-backed searchable multi-select asset picker on `listAssets({ search, membership:'universe', category:'stock' })` with a "whole universe" action and no free-text asset creation; verify a Vitest test for typeahead results, multi-select, whole-universe selection, and that a non-universe string can't be submitted.
- [x] 5.2 Replace the free-text ticker input in `BuildBotCard.tsx` with the new picker and add the sizing fields (sizing method, risk %, ATR period/k, per-name cap, max positions); verify a Vitest test that the form submits a `BotSessionCreateRequest` with a symbol set and sizing params.
- [x] 5.3 Wire `useCreateBotSession` (in `api/bots.ts`) to navigate to the new bot's detail page on success; verify a Vitest test that a successful create triggers navigation to `/bots/:id`.
- [x] 5.4 Update `BotSessionPage.tsx` to render multiple open positions (table) alongside the existing KPI tiles, value chart, and trade ledger; verify a Vitest test rendering a bot with several positions.
- [x] 5.5 Add the dedicated strategy explanation page + route + Bots-area nav entry: render the catalog explanation, an illustrative ECharts crossover chart (deterministic synthetic fast/slow SMA with entry/exit markers), the risk-control/capital-management sections, and loading/error states; verify a Vitest test for the rendered explanation, the illustrative chart option, and the loading/error states. Update `types/api.ts` to mirror the new schemas.

## 6. Verification gates

- [x] 6.1 Backend green: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 6.2 Frontend green: `cd frontend && npm run typecheck && npm run test && npm run build`.
- [x] 6.3 Spec/change valid: `openspec validate add-multi-asset-capital-managed-bots --strict`.
