## Why

Bot orchestrators call an AI model on every decision run, but their spend is invisible:
the dashboard's AI cost breakdown only sums LiteLLM spend tagged with a paper-trading
session id, so orchestrator runs are missing from both its rows and its total, and
nothing in Cadence records how many tokens a run used. Users running orchestrators on a
daily cadence need to see what each one costs.

## What Changes

- **Per-run token usage.** Each decision run records the AI call's token usage (requests,
  input, output and total tokens), read from the agent SDK after the call. A run that
  failed before the AI answered records none.
- **Per-run and per-orchestrator AI cost.** Every run is already tagged in the LiteLLM
  spend log with its own trace id, so:
  - a run's cost is the LiteLLM spend recorded under its trace id;
  - an orchestrator's all-time cost is the sum over its runs.

  No new gateway metadata is needed, and runs made before this change are counted too.
  Costs degrade the same way the existing AI cost figures do:
  - `null` when the cost source is unconfigured or unreachable;
  - `0` when the source is reachable but has no recorded spend.
- **Orchestrator reads.**
  - Orchestrator reads (list and detail) report the all-time AI cost.
  - Run reads report the run's token usage and its cost.
- **Dashboard AI cost breakdown.**
  - The breakdown also lists every active orchestrator as its own row, labelled as an
    orchestrator.
  - The grand total includes orchestrator spend.
- **Orchestrator detail view.**
  - Gains an "AI cost" capital tile.
  - Each run in the history shows its tokens and cost.
- **Migration:** one nullable `usage` JSONB column on `bot_orchestrator_runs`.

## Capabilities

### New Capabilities

<!-- None. -->

### Modified Capabilities

- `bot-orchestrator`:
  - decision run audit (token usage recorded and reported, with per-run cost);
  - orchestrator views (AI cost tile, per-run tokens and cost);
  - a new orchestrator AI cost requirement.
- `dashboard`: the AI cost breakdown includes active orchestrators and their spend in the
  total.
- `app-shell`: the dashboard AI cost panel shows orchestrator rows, labelled as such.

## Impact

- **Backend**:
  - `paper_trading/ai_cost.py`: a batched cost lookup by trace id, sharing the existing
    query helper;
  - `bot_orchestrator/agent.py`: `decide` returns the decision together with its usage;
  - `bot_orchestrator/runs.py`: persist the usage;
  - `bot_orchestrator/models.py`: the `usage` column;
  - `dashboard/service.py`: orchestrator rows and the total;
  - `api/schemas.py`, `api/routers/bot_orchestrators.py`, `api/routers/dashboard.py`;
  - one Alembic migration (applied automatically when the backend container starts).
- **Frontend**:
  - types;
  - `AiCostBreakdown.tsx` (orchestrator rows);
  - `OrchestratorDetailPage.tsx` (AI cost tile, per-run tokens and cost);
  - `OrchestratorsPage.tsx` (an AI cost column).
- **Unchanged**:
  - portfolio AI cost tiles and figures;
  - the LiteLLM gateway and its metadata;
  - orchestrator decision behaviour.
- **Out of scope**:
  - cost for the other non-portfolio AI calls (recommendations, universe evaluation,
    stopped-bot summaries);
  - cost budgets or limits for orchestrators.
