## 1. Accounts and migration

- [x] 1.1 `users` model; owner columns on `portfolios`, `ai_portfolio_events`, `bot_orchestrators`, `bot_sessions`, `broker_orders.account_user_id`; Alembic migration (create, legacy owner, backfill, verify, NOT NULL; downgrade); verify upgrade / downgrade / upgrade + `alembic check` on a scratch DB with seeded rows.
- [x] 1.2 `cadence/accounts.py`: `current_account` (disabled auth → legacy owner; by sub; one-time legacy link by `CADENCE_LEGACY_OWNER`; create), `ensure_can_read` / `ensure_can_act`, scope parsing; setting `CADENCE_LEGACY_OWNER`; verify with pytest.

## 2. Ownership on writes

- [x] 2.1 Creation paths set the owner (portfolio, AI build event, bot, orchestrator; orchestrator-deployed bots inherit); journal records `account_user_id` (bot / AI session owner, acting admin for Admin orders); verify with pytest.

## 3. Scoped reads and actions

- [x] 3.1 Portfolios, paper-trading sessions (incl. KPIs, positions, trades, runs, value history, comparison, sector performance, benchmark / scope / capital / archive / reconcile), AI portfolio (build status, runs, events, rebalance, close): scoped + `owner` in reads; verify with pytest.
- [x] 3.2 Bots (list, detail, KPIs, trades, summary, value history, stop, archive) and orchestrators (list, detail, runs, run detail, start run, stop, archive): scoped + `owner`; verify with pytest.
- [x] 3.3 Dashboard overview / metrics / AI costs scoped to the account; verify with pytest.
- [x] 3.4 `POST /api/v1/recommendations` admin-only; verify with the auth tests.
- [x] 3.5 Cross-user walk test: as user B against every owned-object route of user A → 404 (reads) / 404 (acts); as admin → reads 200, acts 403.

## 4. Frontend

- [x] 4.1 Types gain `owner`; "All users" switch + Owner column for admins (Portfolios, Bots, Orchestrators, Runs); owner line on detail pages and actions hidden for objects that aren't yours; watchlist Discover admin-only; Admin-page shared-account notice; verify with vitest.

## 5. Docs and verification

- [x] 5.1 `.env.example` / `.env.dev.example` / `docs/environments.md`: `CADENCE_LEGACY_OWNER` and the deploy order.
- [x] 5.2 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards; drop `cadence_test` after the model change).
- [x] 5.3 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 5.4 `openspec validate add-user-ownership --strict` passes.
