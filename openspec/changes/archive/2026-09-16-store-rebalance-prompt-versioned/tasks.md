# Tasks

## 1. Data model

- [x] 1.1 Add `RebalancePrompt` ORM model to `ai_portfolio/models.py`: `id` (int
  PK), `version` (int, not null, unique), `instructions` (Text, not null),
  `input_template` (Text, not null), `created_at` (timestamptz, server default).
- [x] 1.2 Add `RebalancePromptNotFoundError` to `ai_portfolio/errors.py`.

## 2. Migration + seed

- [x] 2.1 New Alembic migration with `down_revision = "b8c1e2f3a4d5"`: create
  `rebalance_prompt` with a unique index on `version`; `downgrade()` drops it.
- [x] 2.2 In `upgrade()`, seed version 1 with the current rebalance instructions
  and input-template text, placeholders written as `{name}` tokens
  (`{max_new_assets}`, `{max_web_searches}`, `{risk_profile}`, `{holdings_json}`,
  `{account_json}`, `{candidates_json}`). Seed text embedded as literals (no import
  from app code).

## 3. Service: load the active prompt

- [x] 3.1 Add `get_active_rebalance_prompt(session) -> RebalancePrompt` to
  `ai_portfolio/service.py` (`ORDER BY version DESC LIMIT 1`; raise
  `RebalancePromptNotFoundError` when empty).
- [x] 3.2 In `run_rebalance_event`, load the active prompt before the
  `agent.rebalance(...)` call and pass `instructions` + `input_template` into it.

## 4. Agent: accept templates, render placeholders

- [x] 4.1 Add a brace-safe `_render(template, **values)` helper (explicit token
  replacement, not `str.format`).
- [x] 4.2 Thread `instructions: str` and `input_template: str` through
  `AIPortfolioAgent.rebalance` (Protocol), `OpenAIAIPortfolioAgent.rebalance`,
  `rebalance_ai_portfolio`, and `_run_rebalance`.
- [x] 4.3 `_run_rebalance` renders the instructions template (fills the caps) and
  passes it as the agent's `instructions=`; `_build_rebalance_input` renders the
  passed `input_template` with the run values. Remove `_rebalance_instructions()`
  and the hardcoded input string. Leave the build prompt untouched.

## 5. Tests

- [x] 5.1 `tests/fakes.py`: add `instructions` / `input_template` params to
  `FakeAIPortfolioAgent.rebalance` and record them in `rebalance_calls`.
- [x] 5.2 Agent test: rendering the seeded template equals the previous hardcoded
  output for the same inputs (parity); instructions render fills the caps.
- [x] 5.3 Service test: `get_active_rebalance_prompt` returns the highest version;
  `run_rebalance_event` passes the active prompt's templates to the fake agent; an
  empty table fails the rebalance with `RebalancePromptNotFoundError` and never
  calls the agent.
- [x] 5.4 Update any existing rebalance-path tests/call sites for the new required
  agent params.

## 6. Verification

- [x] 6.1 `uv run ruff check . && uv run mypy src/cadence`.
- [x] 6.2 Drop `cadence_test` DB, then `uv run pytest` (conftest recreates it with
  the new table).
- [x] 6.3 Migration round-trip: `uv run alembic upgrade head` → `downgrade -1` →
  `upgrade head`, and `uv run alembic check` (no drift). Confirm version 1 is
  seeded after upgrade.
