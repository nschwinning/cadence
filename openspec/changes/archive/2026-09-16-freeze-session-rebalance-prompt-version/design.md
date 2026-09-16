# Design

## Column

Add a **non-nullable** integer column `rebalance_prompt_version` to
`paper_trading_sessions`. It holds the `rebalance_prompt.version` the session is
pinned to. No DB-level foreign key to `rebalance_prompt.version`: prompts are
append-only (a pinned version is never deleted), a plain integer keeps the
migration simple, and the resolver already handles a missing version by erroring.
Not indexed (looked up by session PK, never filtered on).

Because the column is non-nullable and set on every build, there is no legacy
null-handling at runtime — the resolver always looks up the pinned version.

## Migration (add nullable → backfill → set not null)

New Alembic revision, `down_revision = "a1d4e7c2b9f8"` (current head). A column
cannot be added `NOT NULL` to a table that already has rows without a default, so
the upgrade runs in three steps:

1. `op.add_column` the column as **nullable**.
2. **Backfill** every existing session to the highest existing prompt version:
   `UPDATE paper_trading_sessions SET rebalance_prompt_version = (SELECT MAX(version) FROM rebalance_prompt) WHERE rebalance_prompt_version IS NULL`.
   Only version 1 exists today, so every session is set to 1. (Guard: if the
   prompt table were empty the subquery is NULL — but the seed migration
   `a1d4e7c2b9f8` runs first and guarantees version 1 exists.)
3. `op.alter_column(..., nullable=False)` to enforce it going forward.

`downgrade()` drops the column.

Because it is a new *column* on an existing table, the persistent `cadence_test`
DB must be dropped so conftest's `create_all` rebuilds it with the column (the
project's known pattern; `create_all` does not ALTER existing tables).

## Freeze at build

`paper_trading/service.create_session(...)` gains a required
`rebalance_prompt_version: int` keyword parameter, stored on the new column.

`ai_portfolio/service.run_build_event(...)` captures the active version at build
and passes it in:

```python
prompt = get_active_rebalance_prompt(session)   # already used by rebalance
...
paper_service.create_session(..., rebalance_prompt_version=prompt.version)
```

If the prompt table were empty, `get_active_rebalance_prompt` raises
`RebalancePromptNotFoundError` — the build fails loudly rather than creating an
unpinned session. This is acceptable: version 1 is always seeded, so a build only
fails here if the environment is misconfigured, which is exactly when it should.

## Resolve at rebalance

Add:

```python
def get_rebalance_prompt_by_version(session, version) -> RebalancePrompt:
    # SELECT ... WHERE version = :version; raise RebalancePromptNotFoundError if absent
```

`run_rebalance_event` resolves the session's frozen version directly:

```python
prompt = get_rebalance_prompt_by_version(session, session_row.rebalance_prompt_version)
```

replacing the current `get_active_rebalance_prompt(session)` call. Everything
downstream (passing `instructions` / `input_template` into `agent.rebalance`,
placeholder rendering in the agent) is unchanged. A pinned-but-missing version
raises `RebalancePromptNotFoundError`, surfaced through the existing `except` as
the event's failure. No active-version fallback exists — the column is
non-nullable, so there is never an unpinned session to fall back for.

## API + frontend surface

- `api/schemas.py`: `PaperTradingSessionRead` gains
  `rebalance_prompt_version: int`.
- Frontend `PaperTradingSession` type gains `rebalance_prompt_version: number`.
  Surface it as a small read-only detail (e.g. "Prompt v{n}") on the session
  header's metadata area. No new controls — freezing is automatic, and there is no
  re-pin UI in this change.

## Testing

- **Migration**: after upgrade the column is present and NOT NULL, and a
  pre-existing session row is backfilled to version 1; round-trip + `alembic check`
  clean.
- **Service (build)**: a built session has `rebalance_prompt_version` set to the
  active version at build; with several versions present it pins the highest.
- **Service (rebalance)**:
  - a session pinned to version N uses N even when a higher version exists
    (assert the templates handed to the fake agent are N's);
  - a session pinned to a missing version fails the rebalance with
    `RebalancePromptNotFoundError` and never calls the agent.
- **Resolver/lookup**: `get_rebalance_prompt_by_version` returns the right row and
  raises on an unknown version.
- **Schema**: `PaperTradingSessionRead` exposes `rebalance_prompt_version`.
- Existing conftest seeds version 1, so sessions built via the test helper carry a
  pin and previously-passing rebalance tests keep working.
