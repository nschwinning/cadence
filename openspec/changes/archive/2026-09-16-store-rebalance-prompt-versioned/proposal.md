# Store the AI rebalancing prompt as a versioned database record

## Why

The AI rebalance agent's prompt is currently a pair of hardcoded strings in
`ai_portfolio/agent.py`: `_rebalance_instructions()` (the system persona and
requirements) and `_build_rebalance_input()` (the per-run input template that
interpolates the risk profile, holdings, account summary, and candidate
universe). Because it lives in code, every prompt tweak requires a code change
and redeploy, and there is no history of what prompt produced a given run.

We want the rebalancing prompt to live in its own database table, **versioned**,
so it can be edited and evolved independently of the code and so the exact
wording that was active can be reconstructed later.

## What Changes

- **New table `rebalance_prompt`** (append-only): one row per prompt version with
  `id`, `version` (integer), `instructions` (text template), `input_template`
  (text template), and `created_at`. The active prompt is the row with the
  highest `version` (`ORDER BY version DESC LIMIT 1`).
- **Both parts of the rebalance prompt move to the DB**: the system instructions
  and the input template, with all runtime placeholders preserved
  (`max_new_assets`, `max_web_searches` in the instructions; `risk_profile`,
  `holdings_json`, `account_json`, `candidates_json` in the input template). The
  agent fills the placeholders at run time exactly as the f-strings do today.
- **The rebalance flow loads the active prompt from the DB** instead of the
  hardcoded functions. The service (which owns the DB session) fetches the active
  version and passes the two templates into the agent seam, keeping the agent
  free of DB coupling.
- **A migration seeds version 1** with the current prompt text verbatim (as
  templates). No behavior change on first deploy: the seeded prompt is byte-for-
  byte the prompt in use today.
- **No API or UI** in this change. New versions are added via the database /
  migrations for now; an editing surface can be a later change.
- **Out of scope**: the *build* prompt (`_builder_instructions` /
  `_build_portfolio_input`) stays hardcoded — the user asked only about the
  rebalancing prompt.

## Impact

- Affected capability: `ai-paper-trading` (the AI rebalance flow gains a
  versioned, DB-backed prompt).
- Affected code: `ai_portfolio/models.py` (new model), `ai_portfolio/service.py`
  (fetch active prompt + pass templates into the agent), `ai_portfolio/agent.py`
  (rebalance entrypoint/Protocol take the templates; render placeholders),
  `ai_portfolio/errors.py` (missing-prompt error), a new Alembic migration
  (create table + seed v1), and tests (`tests/fakes.py` fake-agent signature,
  service/agent tests).
- No frontend changes.
