## Why

Once a paper-trading run is stopped it lingers in the sessions list forever, and
unused portfolios pile up the same way, so the lists that should surface active
work become cluttered with finished experiments. Users need a way to tuck away
completed runs and retired portfolios without losing their history.

## What Changes

- Add a reversible **soft archive** for paper-trading sessions and for
  portfolios. Archiving hides a row from the default lists but keeps all data;
  unarchiving restores it. Nothing is deleted.
- Persist a nullable `archived_at` timestamp on `paper_trading_sessions` and on
  `portfolios` (a row is archived iff `archived_at` is set).
- **Session archive**: only a **stopped** session may be archived; archiving an
  active or paused session is rejected. Unarchiving clears `archived_at`.
- **Portfolio archive**: a portfolio may be archived only when it has **no
  active or paused sessions** (all its sessions are stopped/archived, or it has
  none); otherwise the request is rejected. Unarchiving clears `archived_at`.
- The default session and portfolio list responses **exclude archived rows** and
  gain an `include_archived` flag to opt them back in; the read schemas expose
  `archived_at`.
- Frontend: Archive/Unarchive actions on the paper-trading session list, on the
  session detail page (in the header action corner, shown for a stopped
  session), and on the portfolios list, plus a "Show archived" toggle on both
  list pages.

## Capabilities

### New Capabilities

_None — this extends existing capabilities._

### Modified Capabilities

- `ai-paper-trading`: add archiving of stopped sessions (state transition +
  eligibility rule) and archive-aware session listing/filtering.
- `portfolios`: add archiving of portfolios gated on session state, and
  archive-aware portfolio listing/filtering.
- `app-shell`: surface archive/unarchive controls and a show-archived toggle on
  the session and portfolio views.

## Impact

- **Schema/migration**: new nullable `archived_at` column (+ index) on
  `paper_trading_sessions` and `portfolios`; one Alembic migration off the
  current head.
- **Backend**: `paper_trading` and `portfolios` service + errors + router
  additions (archive/unarchive endpoints, archived filtering); `api/schemas.py`
  gains `archived_at` on `PaperTradingSessionRead`/`PortfolioRead` and an
  `include_archived` list param; cross-domain read of session state for the
  portfolio eligibility check.
- **Frontend**: `api/paperTrading.ts`, `api/portfolios.ts`, `types/api.ts`, the
  paper-trading list + session detail + portfolios list pages, and co-located
  tests.
- No breaking changes: existing rows have `archived_at = NULL` (unarchived), and
  default list behavior is unchanged except that archived rows are now hidden.
