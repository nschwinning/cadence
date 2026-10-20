## 1. Backend — persist the frozen flag

- [x] 1.1 Add `include_watchlist: Mapped[bool]` to `PaperTradingSession` in `paper_trading/models.py` (`Boolean, nullable=False, default=False, server_default="false"`) with a docstring, mirroring `use_fundamentals`.
- [x] 1.2 Add an Alembic migration in `backend/migrations/versions/` that adds `paper_trading_sessions.include_watchlist` (Boolean, non-null, `server_default=sa.false()`), chaining `down_revision` from the current head `a1c3e5f7b9d2`; drop the column on downgrade. Copy `d7e2f9a4c1b3_add_use_fundamentals_session_column.py`.
- [x] 1.3 Thread `include_watchlist` through `paper_trading/service.py::create_session` (new kwarg defaulting to False + set it on the row + docstring).

## 2. Backend — build params and build flow

- [x] 2.1 Add `include_watchlist: bool = False` to `AIBuildParams` in `ai_portfolio/params.py` and carry it in `to_payload` and `from_payload`.
- [x] 2.2 In `ai_portfolio/flows/build.py`, pass `include_watchlist=params.include_watchlist` into `create_session` (persist only; build attaches nothing to candidates).

## 3. Backend — request/response schemas and router

- [x] 3.1 Add `include_watchlist: bool = Field(default=False, ...)` to `AIPortfolioBuildRequest` in `api/schemas.py`.
- [x] 3.2 Add `include_watchlist: bool` to `PaperTradingSessionRead` in `api/schemas.py`.
- [x] 3.3 In `api/routers/ai_portfolio.py`, map `include_watchlist=payload.include_watchlist` into the `AIBuildParams(...)` construction.

## 4. Backend — consume the flag in the rebalance flow

- [x] 4.1 In `ai_portfolio/flows/rebalance.py`, read `watchlist_enabled = bool(session_row.include_watchlist)` (mirror the `fundamentals_enabled` read).
- [x] 4.2 Call `assets_service.list_assets(session, membership=None)` when `watchlist_enabled` else `list_assets(session)`, at both the initial candidate-universe call and the re-query site, so the candidate set is the union of universe + watchlist membership when opted in and universe-only otherwise. Leave the scope/quarantine/trend/eligibility/unexecutable gates unchanged so they apply equally to watchlist assets.

## 5. Frontend — types, build form, fact tile

- [x] 5.1 Add `include_watchlist?: boolean` to `AIPortfolioBuildRequest` and `include_watchlist: boolean` to `PaperTradingSession` in `frontend/src/types/api.ts`.
- [x] 5.2 In `BuildAIPortfolioCard.tsx`, add an `includeWatchlist` state hook (default false), an "Include watchlist assets" toggle card in the toggle grid (copy the company-fundamentals card), and send `include_watchlist` in the `handleSubmit` payload.
- [x] 5.3 In `PaperTradingSessionPage.tsx`, add a read-only "Watchlist assets" fact tile showing On/Off (copy the fundamentals tile).

## 6. Tests

- [x] 6.1 Backend: a watchlist-membership asset appears in the rebalance candidate set when `include_watchlist` is on and is absent when off (copy `test_run_rebalance_event_scope_restricts_candidates` in `test_ai_portfolio_service.py`; capture via `rebalance.rebalance_calls[0]["candidates"]`).
- [x] 6.2 Backend: a crypto-only (or stocks-only) scope session with an out-of-scope watchlist asset still excludes it even with `include_watchlist` on (scope gate still applies to watchlist assets).
- [x] 6.3 Backend: `AIBuildParams` round-trips the flag through `to_payload`/`from_payload`, and `create_session` persists it; `PaperTradingSessionRead` exposes it (dataclass/schema parity).
- [x] 6.4 Frontend vitest: `BuildAIPortfolioCard` sends `include_watchlist: true` when toggled and false/absent by default (copy the existing toggle test); the session fact tile renders On/Off. Update session fixtures carrying `use_fundamentals` to add the new flag.

## 7. Verify

- [x] 7.1 Backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`; confirm the migration round-trips (upgrade + downgrade).
- [x] 7.2 Frontend gates: `cd frontend && npm run -s typecheck && npx vitest run && npm run build`.
- [x] 7.3 `openspec validate add-portfolio-watchlist-opt-in --strict` and `openspec validate --specs`.
