## 1. Backend schema + migration

- [x] 1.1 Add a nullable `ai_portfolio_event_id` `Mapped[uuid.UUID | None]` column (FK to `ai_portfolio_events.id`, indexed) to `SessionRun` in `backend/src/cadence/paper_trading/models.py`, mirroring the field on `PaperTrade`/`ClosedPosition`. Verify: `uv run mypy src/cadence` clean.
- [x] 1.2 Create a new Alembic migration (`down_revision = e5f6a7b8c9d0`) that adds the nullable column, its FK to `ai_portfolio_events`, and an index; `downgrade` drops them. Verify: `uv run alembic upgrade head` then `downgrade -1` round-trips and `uv run alembic check` reports no drift, single linear head.

## 2. Backend recording + read

- [x] 2.1 Add an optional `ai_portfolio_event_id: uuid.UUID | None = None` param to `record_session_run` in `backend/src/cadence/paper_trading/service.py` and set it on the constructed `SessionRun`. Verify: existing paper-trading service tests pass with the default (None).
- [x] 2.2 Pass `ai_portfolio_event_id=event.id` at the four AI-driven `record_session_run` call sites in `backend/src/cadence/ai_portfolio/service.py`: build (`ai_build`), rebalance (`ai_rebalance`), the market-closed skip rebalance run (`ai_rebalance`), and close (`ai_close`). Do NOT set it for the stop-loss run (`STOP_LOSS_RUN_TRIGGER`). Verify: a test asserts an AI build/rebalance run row has `ai_portfolio_event_id == event.id` and the stop-loss run has it null.
- [x] 2.3 Add `ai_portfolio_event_id: uuid.UUID | None` to `SessionRunRead` in `backend/src/cadence/api/schemas.py` (serialized as a nullable string). Verify: reading a session's runs returns the field (event id for AI runs, null otherwise) — API test.

## 3. Frontend link

- [x] 3.1 Add `ai_portfolio_event_id: string | null` to the `SessionRun` type in `frontend/src/types/api.ts`. Verify: `npm run typecheck` clean.
- [x] 3.2 In `RunsPanel` in `frontend/src/pages/paper-trading/PaperTradingSessionPage.tsx`, when a run has a non-null `ai_portfolio_event_id`, wrap the leftmost cell (`ts(r.run_at)`) in a `<Link to={`/runs/${r.ai_portfolio_event_id}`}>` with the `/runs` list-page emerald link styling; otherwise render the timestamp as plain text. Verify: manual render + the tests in 3.3.
- [x] 3.3 Update `frontend/src/pages/paper-trading/PaperTradingSessionPage.test.tsx` run fixtures with `ai_portfolio_event_id`; assert an AI run row links to `/runs/:eventId` and a run with a null reference renders no link. Verify: `npx vitest run src/pages/paper-trading/PaperTradingSessionPage.test.tsx` passes.

## 4. Verification

- [x] 4.1 Backend: `uv run ruff check . && uv run mypy src/cadence && uv run pytest` all green.
- [x] 4.2 Frontend: `npm run typecheck && npx vitest run && npm run build` all green.
- [x] 4.3 `openspec validate link-session-runs-to-ai-events --strict` passes.
