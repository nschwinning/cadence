# Freeze the rebalance prompt version per paper-trading session

## Why

The rebalance prompt is now versioned in the `rebalance_prompt` table, and each
rebalance loads the **active** (highest) version. That means adding a new prompt
version silently changes the prompt used by *every* existing session on its next
rebalance. For reproducibility — an AI-managed run should keep behaving the way it
did when it was created — a session should **freeze** the prompt version it was
built with and always use that version, regardless of later prompt edits.

## What Changes

- **A paper-trading session freezes its rebalance prompt version at build time.**
  When an AI build creates the session, the currently active prompt version is
  captured and stored on the session. Every subsequent rebalance for that session
  uses that pinned version, not whatever is active later.
- **New non-nullable column `rebalance_prompt_version`** (integer) on
  `paper_trading_sessions`, set at build. The migration adds the column nullable,
  **backfills every existing session** to the current highest prompt version (only
  version 1 exists so far), then sets the column `NOT NULL`. There is no valid
  session without a frozen version, so no runtime null-handling is needed.
- **Rebalance resolves the prompt by the session's pinned version** and uses it
  exactly as today (placeholders filled, drives the agent). Because the column is
  non-nullable and prompts are append-only, the pinned version always resolves;
  the only error path is a prompt row that is somehow missing.
- **The frozen version is exposed read-only** on the session read model (and the
  frontend session type) so it is observable; no editing UI and no re-pin flow in
  this change.
- **Out of scope**: choosing the version at build time (auto-freeze the active
  version only), a way to move a session onto a newer prompt version, and the AI
  *build* prompt (still hardcoded).

## Impact

- Affected capability: `ai-paper-trading` (the versioned-prompt requirement gains
  per-session freezing).
- Affected code: `paper_trading/models.py` (new non-nullable column),
  `paper_trading/service.py` (`create_session` accepts the pinned version),
  `ai_portfolio/service.py` (freeze at build; resolve pinned version at rebalance;
  new `get_rebalance_prompt_by_version` / resolver), a new Alembic migration
  (add-nullable → backfill → set-not-null), `api/schemas.py` + the frontend
  session type (expose the field), and tests.
