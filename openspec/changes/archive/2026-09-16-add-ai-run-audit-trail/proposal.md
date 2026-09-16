# Persist AI runs with reasoning + research and link the trades they produce

## Why

Every AI build/rebalance already records an `ai_portfolio_events` row with the
agent's structured output (reasoning: evaluation summary, portfolio health,
per-allocation thesis + confidence). But two things are missing that make it hard
to learn from a run and improve the agent later:

1. **Orders don't point back to their run.** `paper_trades` and `closed_positions`
   carry only a `session_id` and a free-text `signal_type`; there is no reference
   to the AI run (event) that produced them. You cannot go from an opened or closed
   position to the reasoning that caused it.
2. **The research is thrown away.** The agent's `web_search` results (queries + the
   snippets it saw) are consumed inside the run and discarded — only `final_output`
   is kept. That evidence is exactly what we'd want to review to improve the agent's
   reasoning and its research quality.

There is also no way to browse runs: the only view is per-session, summary-only,
with no drill-down into a single run's reasoning, research, and resulting trades.

## What Changes

- **Link trades and closed positions to their AI run.** Add a nullable
  `ai_portfolio_event_id` foreign key to `paper_trades` and `closed_positions`
  (→ `ai_portfolio_events.id`, `ON DELETE SET NULL`). Build and rebalance stamp the
  producing event id on every trade and closed position they record. Non-AI/other
  strategies leave it NULL.
- **Persist the research transcript.** Capture each `web_search` (query + the
  trimmed results the agent received, or an error/budget-exhausted note) during a
  run and store it on the event in a new `research` JSONB column. Capture is done in
  the `web_search` tool via a per-run recorder installed by the service around the
  agent call, so it needs no change to the agent seam and covers build + rebalance.
- **Browse AI run history.** Add read APIs to list AI runs across all sessions
  (newest first, paginated, filterable by type/status) and to open one run's detail:
  its reasoning, its research transcript, and the trades it opened and the positions
  it closed. Expose `research` on the event read model and `ai_portfolio_event_id`
  on the trade/closed-position read models.
- **Frontend: a Runs page + Run detail page.** A new top-level "Runs" view lists all
  AI runs; opening one shows the reasoning, the research (queries + results), the
  opening trades, and the closing positions linked to that run.

Assumption (flag for review): the Runs page lists **all** AI runs — builds and
rebalances, any trigger (manual or daily cron) — not just daily runs, since all
carry reasoning, research, and resulting trades. Filters narrow by type/status.

## Impact

- Affected specs: `ai-paper-trading` — MODIFIED "Record sessions, trades, runs, and
  closed positions" (trades/closed positions reference their run; runs persist
  reasoning + research), MODIFIED "Read paper-trading session data" (research
  exposed), ADDED "Browse AI run history and details". `app-shell` — MODIFIED
  "Persistent application shell" (add a Runs nav entry), ADDED "AI run history and
  detail views".
- Affected code (backend, schema): Alembic migration adding `research` (JSONB) to
  `ai_portfolio_events` and `ai_portfolio_event_id` (FK, indexed, nullable) to
  `paper_trades` and `closed_positions`; matching ORM columns in
  `ai_portfolio/models.py` and `paper_trading/models.py`.
- Affected code (backend, behavior): `agents/tools.py` (per-run web-search recorder
  + a `note_web_search` capture hook in the tool); `ai_portfolio/service.py`
  (`run_build_event`/`run_rebalance_event` wrap the agent call in the recorder,
  persist `research` on the event, and pass the event id into
  `_record_trades`/`_apply_rebalance_trades`); `paper_trading/service.py`
  (`record_trade`/`record_closed_position` accept an optional `ai_portfolio_event_id`;
  add `list_ai_runs`/`count_ai_runs` and event-scoped trade/closed-position reads);
  `api/routers/ai_portfolio.py` (new `GET /ai-portfolio/runs` and
  `GET /ai-portfolio/runs/{event_id}`); `api/schemas.py` (research + FK fields, run
  list/detail response models).
- Affected code (frontend): `App.tsx` route registration + shell nav entry;
  `api/aiPortfolio.ts` (fetchers, query keys, `useAIRuns`/`useAIRunDetail`);
  `types/api.ts`; new `pages/runs/RunsPage.tsx` + `RunDetailPage.tsx` with
  co-located tests.
- Tests: web-search recorder unit tests; service tests that trades/closed positions
  are stamped with the event id and research is persisted (including on failure);
  API tests for the runs list + detail; frontend tests for both pages.
- Backwards compatibility: the new columns are nullable; existing rows (and non-AI
  strategy trades) remain valid with NULL links and NULL research.
