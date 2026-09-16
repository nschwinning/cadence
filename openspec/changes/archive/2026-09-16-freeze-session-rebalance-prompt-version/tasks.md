# Tasks

## 1. Schema + migration

- [x] 1.1 Add non-nullable `rebalance_prompt_version: Mapped[int]` column to
  `PaperTradingSession` in `paper_trading/models.py`.
- [x] 1.2 Create an Alembic migration (`down_revision = "a1d4e7c2b9f8"`):
  add the column nullable → backfill every session to `MAX(rebalance_prompt.version)`
  → `alter_column` to `NOT NULL`; `downgrade()` drops it.
- [x] 1.3 Drop `cadence_test` so conftest's `create_all` rebuilds the table with
  the new column; run `alembic upgrade head` + `alembic check` (no drift) and a
  down/up round-trip, confirming an existing session backfills to version 1.

## 2. Freeze at build

- [x] 2.1 Add required `rebalance_prompt_version: int` keyword param to
  `paper_trading/service.create_session(...)`, stored on the new column.
- [x] 2.2 In `run_build_event`, capture the active prompt
  (`get_active_rebalance_prompt(session)`) and pass its `.version` into
  `create_session` so the new session is pinned at build time.

## 3. Resolve at rebalance

- [x] 3.1 Add `get_rebalance_prompt_by_version(session, version) -> RebalancePrompt`
  to `ai_portfolio/service.py` (raises `RebalancePromptNotFoundError` if absent).
- [x] 3.2 In `run_rebalance_event`, resolve the prompt via
  `get_rebalance_prompt_by_version(session, session_row.rebalance_prompt_version)`
  instead of `get_active_rebalance_prompt`.

## 4. API + frontend surface

- [x] 4.1 Add `rebalance_prompt_version: int` to `PaperTradingSessionRead` in
  `api/schemas.py`.
- [x] 4.2 Add `rebalance_prompt_version: number` to the frontend
  `PaperTradingSession` type and show it read-only (e.g. "Prompt v{n}") on the
  session header.

## 5. Tests

- [x] 5.1 Migration test: an existing session row backfills to version 1 and the
  column is NOT NULL after upgrade.
- [x] 5.2 Build test: a built session pins the active version (and the highest when
  several exist).
- [x] 5.3 Rebalance test: a session pinned to version N uses N even when a higher
  version exists (assert the templates handed to the fake agent are N's).
- [x] 5.4 Rebalance test: a session pinned to a missing version fails with
  `RebalancePromptNotFoundError` and never invokes the agent.
- [x] 5.5 Lookup test: `get_rebalance_prompt_by_version` returns the right row and
  raises on an unknown version.
- [x] 5.6 Schema test: `PaperTradingSessionRead` exposes `rebalance_prompt_version`.

## 6. Verification

- [x] 6.1 `uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 6.2 Frontend `npm run typecheck && npx vitest run && npm run build`.
