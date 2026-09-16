## 1. Schema & migration

- [x] 1.1 Add `archived_at: Mapped[datetime | None]` (nullable, indexed) to `PaperTradingSession` in `paper_trading/models.py`.
- [x] 1.2 Add `archived_at: Mapped[datetime | None]` (nullable, indexed) to `Portfolio` in `portfolios/models.py`.
- [x] 1.3 Create one Alembic migration (`down_revision = "a2c5e8d4f1b7"`) adding both nullable columns + their indexes; `downgrade` drops them. Verify with an upgrade→downgrade round-trip and `alembic check` (no drift).

## 2. Paper-trading session archive (backend)

- [x] 2.1 Add `SessionNotArchivableError` to `paper_trading/errors.py`.
- [x] 2.2 In `paper_trading/service.py`, add `archive_session(db, id)` (raise `SessionNotArchivableError` unless status is STOPPED; set `archived_at = now`) and `unarchive_session(db, id)` (clear `archived_at`); both raise `SessionNotFoundError` for unknown id.
- [x] 2.3 Add `include_archived: bool = False` to `list_sessions` and `count_sessions`; when false, filter `archived_at IS NULL`, composing with the existing status filter.
- [x] 2.4 Add `archived_at: datetime | None` to `PaperTradingSessionRead` in `api/schemas.py`.
- [x] 2.5 In `api/routers/paper_trading.py`, add `POST /sessions/{id}/archive` and `/unarchive` (return updated read model; map not-found→404, not-archivable→409) and an `include_archived` query param on `GET /sessions`.

## 3. Portfolio archive (backend)

- [x] 3.1 Add `PortfolioNotArchivableError` to `portfolios/errors.py`.
- [x] 3.2 In `portfolios/service.py`, add `archive_portfolio(db, id)` (raise `PortfolioNotArchivableError` if any of the portfolio's sessions has status active/paused — query `PaperTradingSession`; else set `archived_at = now`) and `unarchive_portfolio(db, id)` (clear `archived_at`); both raise `PortfolioNotFoundError` for unknown id.
- [x] 3.3 Add `include_archived: bool = False` to `list_portfolios` and `count_portfolios`; when false, filter `archived_at IS NULL`, composing with `include_legacy`.
- [x] 3.4 Add `archived_at: datetime | None` to `PortfolioRead` in `api/schemas.py`.
- [x] 3.5 In `api/routers/portfolios.py`, add `POST /{id}/archive` and `/unarchive` (map not-found→404, not-archivable→409) and an `include_archived` query param on `GET /portfolios`.

## 4. Backend tests

- [x] 4.1 `paper_trading` service tests: archive a stopped session; reject archiving active/paused; unarchive clears; default list hides archived; `include_archived=True` includes them; unknown id raises.
- [x] 4.2 `paper_trading` API tests: archive/unarchive happy paths (200 + `archived_at`); 409 archiving a non-stopped session; 404 unknown; `include_archived` query filters the list.
- [x] 4.3 `portfolios` service tests: archive a portfolio with no active/paused sessions (and one with none); reject when an active/paused session exists; unarchive clears; default list hides archived; `include_archived=True` includes; unknown id raises.
- [x] 4.4 `portfolios` API tests: archive/unarchive happy paths; 409 when a session is active; 404 unknown; `include_archived` query filters the list.

## 5. Frontend

- [x] 5.1 Add `archived_at?: string | null` to `PaperTradingSession` and `Portfolio` in `types/api.ts`.
- [x] 5.2 In `api/paperTrading.ts`, thread `include_archived` through the sessions list key + fetcher, and add `useArchiveSession` / `useUnarchiveSession` mutation hooks (POST, invalidate the sessions list).
- [x] 5.3 In `api/portfolios.ts`, thread `include_archived` through the portfolios list key + fetcher, and add `useArchivePortfolio` / `useUnarchivePortfolio` mutation hooks (POST, invalidate the portfolios list).
- [x] 5.4 Paper-trading session list page: add a "Show archived" toggle, per-row Archive (only for a stopped, non-archived session) / Unarchive (for archived) actions, and an "Archived" marker.
- [x] 5.5 Session detail page: add an Archive/Unarchive control in the header action corner (shown for a stopped session), reusing the existing action button/feedback split pattern.
- [x] 5.6 Portfolios list page: add a "Show archived" toggle, per-row Archive (only when the portfolio has no active/paused session) / Unarchive actions, and an "Archived" marker.
- [x] 5.7 Co-located Vitest tests: toggling "Show archived" refetches with the flag; archive/unarchive actions call the right endpoints and update the list; the session-detail archive control appears only when stopped.

## 6. Verification

- [x] 6.1 Backend: `uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 6.2 Migration: `uv run alembic upgrade head`, `downgrade -1`, `upgrade head`, and `alembic check` (no drift).
- [x] 6.3 Frontend: `npm run typecheck && npx vitest run && npm run build`.
- [x] 6.4 `openspec validate add-archive-sessions-and-portfolios --strict`.
