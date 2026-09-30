## Why

On the paper-trading session-detail page, the "Runs" table lists each of a session's execution runs but the rows are dead text — a user cannot jump from a run to the AI reasoning, research, and trades behind it. Trades and closed positions already carry a reference to the AI-portfolio event that produced them (and the run-detail view exists), but session runs do not, so there is nothing to link them to. This closes that gap so an AI-driven run row can open its run detail.

## What Changes

- Session-run records gain an optional reference to the AI-portfolio event that produced them. The four AI-driven run creation sites (build, rebalance, the market-closed skip run, and close) SHALL record this reference; deterministic stop-loss runs and any scheduled/manual scanner runs SHALL leave it empty.
- A session's run read SHALL expose this reference (absent when the run was not produced by an AI event).
- On the session-detail view, a run row backed by an AI-portfolio event SHALL link to that event's existing run-detail view; a run with no such reference SHALL remain non-interactive text.
- Schema: a new nullable `ai_portfolio_event_id` foreign-key column on the `session_runs` table (mirrors the existing reference on trades and closed positions), added via an Alembic migration. Existing rows stay null; no backfill.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ai-paper-trading`: the "Record sessions, trades, runs, and closed positions" requirement extends run recording so AI-driven runs reference the AI-portfolio event that produced them; the "Read paper-trading session data" requirement exposes that reference on the run read.
- `app-shell`: the "Portfolio and paper-trading views" requirement makes a session's run rows link to the run-detail view when the run is backed by an AI-portfolio event.

## Impact

- Backend: `paper_trading/models.py` (`SessionRun`), a new Alembic migration (nullable FK column + index), `paper_trading/service.py` (`record_session_run` gains an optional param), `ai_portfolio/service.py` (four AI run sites pass `event.id`), `api/schemas.py` (`SessionRunRead` gains the field).
- Frontend: `types/api.ts` (`SessionRun` gains the field), `pages/paper-trading/PaperTradingSessionPage.tsx` (`RunsPanel` conditionally links the run row).
- No config change. No change to non-AI run recording behavior (stop-loss/scheduled/manual runs stay null).
