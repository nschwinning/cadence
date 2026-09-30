## Context

See proposal.md — Why. `session_runs` is a per-execution log with no reference to the AI-portfolio event behind a run. `paper_trades` and `closed_positions` already carry a nullable `ai_portfolio_event_id` FK (migration `e1f4c2a7b9d5`) and the run-detail view already exists (keyed by the AI-portfolio event id). At all four AI-driven run creation sites in `ai_portfolio/service.py` the `AIPortfolioEvent` (`event`) is already in scope where `record_session_run` is called — it is simply not persisted on the run.

## Goals / Non-Goals

**Goals**
- Persist, on AI-driven runs, a reference to the AI-portfolio event that produced them, mirroring the existing trade/closed-position reference.
- Expose that reference on the run read so the UI can link a run row to its detail view.

**Non-Goals**
- No dedicated `SessionRun` detail page — AI-driven runs reuse the existing `/runs/:id` run-detail view keyed by the AI-portfolio event id.
- No linking or detail target for non-AI runs (stop-loss, scheduled/manual scanner runs) — they stay null and non-interactive.
- No backfill of existing rows; no change to run-list ordering or pagination.

## Decisions

- **Reuse `ai_portfolio_event_id` FK pattern rather than a new detail entity.** Adds a nullable `ai_portfolio_event_id` UUID column to `session_runs` with an FK to `ai_portfolio_events` and an index, exactly like `paper_trades`/`closed_positions`. Alternative — a standalone `SessionRun` detail endpoint/route — was rejected as a larger net-new surface for no added user value (the run detail the user wants already exists for the AI event).
- **Nullable, no backfill.** Runs predating this change, and all non-AI runs (stop-loss, scheduled/manual), legitimately have no producing AI event, so null is the correct absence marker. This keeps the migration a pure additive column + index with a trivial `downgrade`, preserving the single linear head (`down_revision = e5f6a7b8c9d0`).
- **Populate only where an AI event exists.** Thread an optional `ai_portfolio_event_id` (default `None`) through `record_session_run`; pass `event.id` at the four AI sites (build, rebalance, market-closed skip, close). The stop-loss run and any scheduled/manual runs pass nothing, leaving it null.
- **Frontend links the run's leftmost cell** (the timestamp) when the reference is present, using the same emerald link styling as the `/runs` list page; otherwise it renders the timestamp as plain text. This matches how the trades/closed-positions tables link their leftmost identifying cell.

## Risks / Trade-offs

- A run and its AI event are recorded in the same transaction path; the event exists before the run is recorded, so the FK is always satisfiable when set. The market-closed skip run records the event too, so its reference is populated even though it executed no orders — acceptable, since its detail view is still meaningful.
- Mixed linked/unlinked rows in one table could look inconsistent, but this faithfully reflects that only AI-driven runs have a detail view; non-AI runs have nothing to show.

## Migration Plan

- New Alembic revision, `down_revision = e5f6a7b8c9d0` (current head). `upgrade`: add nullable `ai_portfolio_event_id` UUID column to `session_runs`, an FK to `ai_portfolio_events.id`, and an index. `downgrade`: drop the index, FK, and column. No data migration.

## Open Questions

None.
