## 1. Schema: link trades/positions to runs + store research

- [x] 1.1 `ai_portfolio/models.py`: add `research: Mapped[list[dict[str, Any]] | None]` (JSONB, nullable) to `AIPortfolioEvent`, documented as the per-run web-search transcript.
- [x] 1.2 `paper_trading/models.py`: add `ai_portfolio_event_id: Mapped[uuid.UUID | None]` to `PaperTrade` and `ClosedPosition` — `ForeignKey("ai_portfolio_events.id", ondelete="SET NULL")`, nullable, indexed. Nullable so non-AI trades and legacy rows stay valid.
- [x] 1.3 New Alembic migration (`down_revision = "c4e7a1f9b2d3"`): add the `research` column and the two FK columns + their indexes; `downgrade` drops them. Keep a single linear head. Verify `alembic upgrade head` then `downgrade base`, and `alembic check` reports no drift.

## 2. Capture the research transcript

- [x] 2.1 `agents/tools.py`: add a per-run recorder — a `ContextVar[list | None]` and a `record_web_searches()` context manager yielding a fresh list, plus a `note_web_search(query, results, error=None)` helper that appends `{query, results, error}` to the active log when one is installed (no-op otherwise). Because it appends to a shared list (never rebinds), a recorder installed OUTSIDE `asyncio.run` is still seen by the tool inside it.
- [x] 2.2 `agents/tools.py`: call `note_web_search(...)` from `_run_web_search` — recording the query and the trimmed results on success, and a note (query + `error`) on the budget-exhausted / error branches. Keep the value returned to the agent unchanged.

## 3. Thread the run id + research through the service

- [x] 3.1 `paper_trading/service.py`: `record_trade(...)` and `record_closed_position(...)` gain an optional `ai_portfolio_event_id: uuid.UUID | None = None`, persisted on the row. Existing callers (momentum/other strategies) keep passing nothing → NULL.
- [x] 3.2 `ai_portfolio/service.py`: `_record_trades(...)` (build) and `_apply_rebalance_trades(...)` (rebalance) take the `event_id` and forward it to `record_trade`/`record_closed_position`.
- [x] 3.3 `ai_portfolio/service.py`: in `run_build_event` and `run_rebalance_event`, wrap the agent call in `with record_web_searches() as research:` (bind at entry so partial research survives an agent error), persist `research` via `_finish_event(..., research=research)` on the terminal success/partial/skip path, and also store any captured research on the failure path (`_fail_event(..., research=research)`). Pass the event id into the trade-recording helpers. Do not capture/store research on the market-closed skip branch that returns before the agent runs (research stays empty).

## 4. Read APIs: list runs + run detail

- [x] 4.1 `api/schemas.py`: add `research: list[dict[str, Any]] | None` to `AIPortfolioEventRead`; add `ai_portfolio_event_id: uuid.UUID | None` to `PaperTradeRead` and `ClosedPositionRead`.
- [x] 4.2 `api/schemas.py`: add `AIPortfolioRunSummary` (slim: id, session_id, portfolio_id, event_type, status, orders_executed count from `actions_taken`, duration_ms, created_at, error), `AIPortfolioRunListResponse {items, total}`, and `AIPortfolioRunDetail {event: AIPortfolioEventRead, trades: list[PaperTradeRead], closed_positions: list[ClosedPositionRead]}`.
- [x] 4.3 `ai_portfolio/service.py` (or `paper_trading/service.py`): add `list_ai_runs(session, *, limit, offset, event_type=None, status=None)` + `count_ai_runs(...)`, and event-scoped reads `get_trades_by_event(event_id)` / `get_closed_positions_by_event(event_id)`.
- [x] 4.4 `api/routers/ai_portfolio.py`: add `GET /ai-portfolio/runs` (paginated list, optional `event_type`/`status` query filters) → `AIPortfolioRunListResponse`, and `GET /ai-portfolio/runs/{event_id}` → `AIPortfolioRunDetail` (404 when unknown). Verify `mypy` clean.

## 5. Frontend: Runs page + Run detail page

- [x] 5.1 `types/api.ts`: add `AIRunSummary`, `AIRunDetail`, `research` on the event type, and `ai_portfolio_event_id` on the trade/closed-position types.
- [x] 5.2 `api/aiPortfolio.ts`: add fetchers (`listAIRuns`, `getAIRun`), extend the query-key factory, and add `useAIRuns()` / `useAIRunDetail(id)` hooks (mirror existing patterns).
- [x] 5.3 New `pages/runs/RunsPage.tsx`: a cross-session table of all AI runs (type, status badge, orders executed, duration, created_at, error), each row linking to its detail. Register the `/runs` route in `App.tsx` and add a "Runs" entry to the shell navigation.
- [x] 5.4 New `pages/runs/RunDetailPage.tsx` (route `/runs/:id`): render the run's reasoning (from `result_payload`), the research transcript (query + results per search), the opening trades, and the closing positions linked to the run. Reuse existing badges/panels where practical.

## 6. Tests

- [x] 6.1 `agents/tools` tests: `note_web_search` records within `record_web_searches` and is a no-op outside it; `_run_web_search` records a search's query+results and records an error note on the budget-exhausted branch.
- [x] 6.2 Service tests: build and rebalance stamp `ai_portfolio_event_id` on every recorded trade and closed position; the producing run's `research` is persisted; research captured before a mid-run failure is still stored on the failed event; the market-closed skip records no research.
- [x] 6.3 Update `tests/fakes.py` `FakeAIPortfolioAgent` to optionally emit research entries (via `note_web_search`) so service persistence can be asserted without network.
- [x] 6.4 API tests: `GET /ai-portfolio/runs` lists runs across sessions newest-first with filters + total; `GET /ai-portfolio/runs/{id}` returns the event (with research), its opening trades, and its closing positions; 404 for an unknown id.
- [x] 6.5 Frontend tests (vitest): `RunsPage` renders rows and links; `RunDetailPage` renders reasoning, research, opening trades, and closing positions from a mocked run detail.

## 7. Verification

- [x] 7.1 Backend: `uv run pytest` green, `uv run ruff check .` clean, `uv run mypy src/cadence` clean; migration round-trip (`upgrade head` → `downgrade base`) and `alembic check` clean.
- [x] 7.2 Frontend: `npm run typecheck`, `npx vitest run`, `npm run build` all green.
- [x] 7.3 `openspec validate add-ai-run-audit-trail --strict` passes.
