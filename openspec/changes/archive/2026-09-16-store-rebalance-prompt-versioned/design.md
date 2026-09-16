# Design

## Table and model

New table `rebalance_prompt`, append-only, one row per version:

| column          | type                     | notes                                    |
| --------------- | ------------------------ | ---------------------------------------- |
| `id`            | integer PK               | surrogate key                            |
| `version`       | integer, not null, unique | monotonically increasing; active = MAX  |
| `instructions`  | text, not null           | system-instructions template            |
| `input_template`| text, not null           | per-run input template                  |
| `created_at`    | timestamptz, not null, server_default now() | audit                |

ORM model `RebalancePrompt` lives in `ai_portfolio/models.py` (same domain as the
rebalance flow). A unique constraint/index on `version` enforces the append-only
invariant at the DB level. The active row is resolved with
`ORDER BY version DESC LIMIT 1` — no `is_active` flag to keep in sync (per the
chosen "latest = active" model).

## Placeholders and rendering

The two templates keep the exact placeholders the current f-strings interpolate:

- **instructions**: `{max_new_assets}`, `{max_web_searches}`
  (from `settings.AI_PORTFOLIO_MAX_NEW_ASSETS` / `AI_PORTFOLIO_MAX_WEB_SEARCHES`).
- **input_template**: `{risk_profile}`, `{holdings_json}`, `{account_json}`,
  `{candidates_json}`.

Rendering uses **explicit token replacement** (a small `_render(template, **values)`
helper that does `template.replace("{name}", value)` for each known key), *not*
`str.format`. Rationale: the rendered input embeds JSON blobs, and future prompt
edits may include literal `{`/`}`; `str.format` would choke on stray braces, while
explicit replacement is brace-safe and only touches the known tokens. The set of
tokens is fixed and small, so this stays simple.

The rendered output must be byte-for-byte identical to today's f-string output for
the same inputs — this is asserted in tests (seeded-v1 parity) and is the reason
the seed text is copied verbatim with the interpolations turned back into tokens.

## Wiring: service loads, agent renders

The agent seam stays DB-free. The service (`run_rebalance_event`) already holds
the `Session`, so it fetches the active prompt there and passes the two template
strings into the agent:

- `ai_portfolio/service.py`: add `get_active_rebalance_prompt(session) ->
  RebalancePrompt` (raises `RebalancePromptNotFoundError` when the table is
  empty). In `run_rebalance_event`, load it before the `agent.rebalance(...)` call
  and pass `instructions=prompt.instructions, input_template=prompt.input_template`.
- `ai_portfolio/agent.py`: `AIPortfolioAgent.rebalance` Protocol,
  `OpenAIAIPortfolioAgent.rebalance`, `rebalance_ai_portfolio`, and
  `_run_rebalance` gain `instructions: str` and `input_template: str` parameters.
  `_run_rebalance` uses `instructions` (rendered with the caps) as the agent's
  `instructions=`; `_build_rebalance_input` becomes a renderer over
  `input_template`. `_rebalance_instructions()` is removed (its text moves to the
  seed); `_build_rebalance_input`'s hardcoded string is removed in favor of the
  passed template.
- `_builder_instructions()` / `_build_portfolio_input()` (the *build* prompt) are
  untouched — out of scope.

Because the two new parameters are required on the seam, every caller and the fake
must pass them; the service is the only production caller.

## Migration and seed

New Alembic migration, `down_revision = "b8c1e2f3a4d5"` (current head), becomes the
new head. `upgrade()`:

1. `op.create_table("rebalance_prompt", ...)` with the columns above + unique index
   on `version`.
2. Seed version 1: `op.bulk_insert` (or a plain `op.execute` INSERT) with the
   current instructions and input-template text, placeholders written as `{name}`
   tokens. The seed text is embedded in the migration as string literals so the
   migration is self-contained and reproducible (it does not import from
   application code, which may drift).

`downgrade()` drops the table. Round-trip (`upgrade` → `downgrade` →
`upgrade`) and `alembic check` (no drift vs. the model) must pass.

Note: the persistent `cadence_test` database is created once by the test
`conftest` via `create_all`, which does not add new tables to an already-built DB.
Per the project's established pattern, the test DB is dropped
(`DROP DATABASE cadence_test`) so conftest recreates it with the new table before
running the suite.

## Error handling

Add `RebalancePromptNotFoundError` to `ai_portfolio/errors.py`. It is raised by
`get_active_rebalance_prompt` when the table is empty and surfaces through
`run_rebalance_event`'s existing `except Exception` as the event's failure
reason — the rebalance is marked `failed` with a clear message and the agent is
never called. In practice the seed guarantees a row exists; this guards the
misconfigured/empty-table case.

## Testing

- **Agent render parity**: `_build_rebalance_input(...)` rendered from the seeded
  template equals the previous hardcoded output for the same inputs; instructions
  render fills the caps.
- **Service**: `get_active_rebalance_prompt` returns the highest version when
  several exist; `run_rebalance_event` passes the active prompt's templates into
  the (fake) agent — asserted via `FakeAIPortfolioAgent.rebalance_calls`; an empty
  table fails the rebalance with `RebalancePromptNotFoundError` and does not call
  the agent.
- **Fake**: `FakeAIPortfolioAgent.rebalance` gains the `instructions` /
  `input_template` params and records them.
- **Migration**: create + seed v1 present after `upgrade`; round-trip clean;
  seeded text round-trips to the expected rendered prompt.
