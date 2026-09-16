## Context

Sessions (`paper_trading_sessions`) and portfolios (`portfolios`) are never
removed today. `PaperTradingSession` has a `status` enum (active/paused/stopped)
and cascades to its child tables; `Portfolio` has no status. Listing lives in the
service layer (`paper_trading.service.list_sessions/count_sessions`,
`portfolios.service.list_portfolios/count_portfolios`) behind thin routers, and the
read schemas are `PaperTradingSessionRead` / `PortfolioRead` in `api/schemas.py`.
Alembic owns the schema (head `a2c5e8d4f1b7`); the ORM is the autogenerate source.
The frontend mirrors each resource with a query-key factory + raw fetchers +
TanStack Query hooks in `api/paperTrading.ts` / `api/portfolios.ts`, typed in
`types/api.ts`.

## Goals / Non-Goals

**Goals:**
- Reversible soft-archive for stopped sessions and for portfolios, driven by a
  single nullable `archived_at` column per table (archived ⇔ `archived_at IS NOT
  NULL`).
- Hide archived rows from default lists; opt back in via `include_archived`.
- Enforce eligibility: only a stopped session archives; a portfolio archives only
  when it has no active/paused session.
- UI to archive/unarchive on the session list, session detail, and portfolio list,
  plus a "Show archived" toggle on both lists.

**Non-Goals:**
- No hard delete, no bulk archive, no auto-archive on stop.
- No change to session status semantics or to cascade behavior.
- No pagination rework; keep the existing single-page list shape.

## Decisions

- **`archived_at TIMESTAMPTZ NULL` (not a boolean).** A nullable timestamp both
  encodes the archived flag and records when it happened, at no extra cost. A row
  is archived iff the column is set. Add a plain index on each column so the
  default "not archived" filter stays cheap. One Alembic migration,
  `down_revision = "a2c5e8d4f1b7"`, adds both columns + indexes; `downgrade` drops
  them. Existing rows default to NULL (unarchived), so behavior is unchanged apart
  from archived rows being hidden.

- **Service-layer state transitions with domain errors.** Add
  `archive_session(db, id) / unarchive_session(db, id)` to `paper_trading.service`
  and `archive_portfolio(db, id) / unarchive_portfolio(db, id)` to
  `portfolios.service`. `archive_session` raises a new
  `SessionNotArchivableError` unless `status == STOPPED`; `archive_portfolio`
  raises a new `PortfolioNotArchivableError` when any of its sessions is
  active/paused. Unarchive is unconditional (clears the timestamp). Unknown id
  raises the existing `SessionNotFoundError` / `PortfolioNotFoundError`. Routers
  map: not-found → 404, not-archivable → 409.

- **Cross-domain eligibility read.** The portfolio archivability check needs
  session state. `portfolios.service.archive_portfolio` queries
  `PaperTradingSession` filtered to the portfolio for any row with status in
  {active, paused}. Importing the `PaperTradingSession` model into the portfolios
  service is a read-only query and avoids a circular import (paper_trading does not
  import portfolios). Keep the query in the service, router stays thin.

- **Endpoints.** `POST /api/v1/paper-trading/sessions/{id}/archive` and
  `/unarchive`; `POST /api/v1/portfolios/{id}/archive` and `/unarchive`. Each
  returns the updated read model (200). This matches the existing action-style
  POST convention (e.g. session close/rebalance) rather than PATCH.

- **Listing filter.** Add `include_archived: bool = False` to
  `list_sessions/count_sessions` and `list_portfolios/count_portfolios`; when
  false, filter `archived_at IS NULL`. Surface it as an `include_archived` query
  param on both list endpoints. The session filter composes with the existing
  `status` filter; the portfolio filter composes with `include_legacy`. Add
  `archived_at: datetime | None` to both read schemas.

- **Frontend.** Add `archived_at?: string | null` to the `PaperTradingSession` and
  `Portfolio` types. Add `include_archived` to the list fetchers/keys and
  archive/unarchive mutation hooks (POST, invalidating the relevant list keys) in
  `api/paperTrading.ts` and `api/portfolios.ts`. Each list page gets a local
  "Show archived" toggle (drives the query param) and, per row, an Archive button
  (shown only when eligible) or an Unarchive button (when archived), with an
  "Archived" marker. On the session detail page, reuse the header action-corner
  pattern: a stopped session shows an Archive/Unarchive control alongside the
  existing rebalance/close actions (mirroring the `useCloseAction` + button/feedback
  split already in place).

## Risks / Trade-offs

- **Archived portfolio with a still-active session drifting.** Eligibility is
  checked at archive time; a later flow can't reactivate a session on an archived
  portfolio through the AI paths (those operate on active sessions), so the archived
  set stays consistent. Unarchive is always available as an escape hatch.
- **Test DB schema.** The test harness builds schema from ORM metadata, so the new
  columns appear automatically in tests; the migration is verified separately via
  an upgrade/downgrade round-trip and `alembic check`.
- **List semantics change.** Clients that previously saw stopped rows in the
  default list will no longer see them once archived — intended, and opt-out via
  `include_archived=true`.
