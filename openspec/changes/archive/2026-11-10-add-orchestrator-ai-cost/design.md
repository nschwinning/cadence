## Context

- **How spend is recorded.** The LiteLLM gateway stamps each agent call's spend-log
  metadata from `llm_trace(...)`:
  - every call gets `cadence_trace_id`;
  - portfolio runs additionally get `cadence_session_id`;
  - orchestrator runs already call `llm_trace(f"orchestrator-run-{run.id}")`, so each
    orchestrator call is tagged with its run's trace id.
- **How cost is read.** `paper_trading/ai_cost.py` is the one module coupled to LiteLLM's
  `LiteLLM_SpendLogs` schema. It sums `spend` by `cadence_session_id`, either for one
  session or batched (`session_ai_costs_usd`). Its degradation contract is:
  - `None` when unconfigured or failing;
  - `{}` for no ids;
  - ids with no spend absent from the map, so callers show `0`.
- **Token usage.** The openai-agents SDK exposes usage after a run as
  `result.context_wrapper.usage` (`requests`, `input_tokens`, `output_tokens`,
  `total_tokens`). Cadence discards it today.

## Goals / Non-Goals

**Goals:**
- Accurate per-run and per-orchestrator cost from the authoritative LiteLLM spend, including
  runs made before this change.
- Token usage stored on the run itself, so it is visible even without LiteLLM.
- A dashboard total that really includes orchestrator spend.

**Non-Goals:**
- Changing the gateway, its metadata keys, or how portfolio cost is computed.
- Cost for recommendations, the universe evaluation or bot summaries.
- Cost budgets or alerts.

## Decisions

**1. Cost by run trace id, not a new orchestrator metadata key.**
- A run's cost is `SUM(spend)` where `cadence_trace_id` equals the run's trace id.
- An orchestrator's cost is the sum over its runs.
- This needs no gateway change and also attributes runs made before this change.
- Rejected: stamping a new `cadence_orchestrator_id` key. It needs a gateway change and
  cannot attribute existing runs.
- The trace id format moves into one helper, `run_trace_id(run_id)` in `runs.py`, used
  by both `llm_trace` and the cost lookup so they cannot drift.

**2. Generalise the cost query, don't duplicate it.**
- `ai_cost.py` gains a private `_costs_by_metadata_key(key, values)` holding the batched
  query and its degradation contract.
- The existing `session_ai_costs_usd` delegates to it (behaviour unchanged).
- A new `trace_ai_costs_usd(trace_ids)` uses the trace key.
- The single-session helper is untouched.
- Orchestrator totals are aggregated in Python from one batched run-cost query: gather
  the run ids of the orchestrators being read, query once, then sum per orchestrator.
- Run counts are small (about 250 a year per daily orchestrator), so an `ANY(:ids)` list
  is fine.

**3. Usage travels with the decision.**
- `OrchestratorAgent.decide` returns an `OrchestratorAgentResult(decision, usage)`, where
  `usage: RunUsage | None` is a frozen dataclass with `requests`, `input_tokens`,
  `output_tokens` and `total_tokens`.
- The production agent reads `result.context_wrapper.usage`; the fake agent returns a
  canned usage.
- Rejected: a mutable `last_usage` attribute on the agent, which is implicit and fragile
  if an agent instance is ever reused.
- `execute_run` stores `usage` as JSONB right after the AI answers.
- Skipped runs and runs that fail before an answer keep `usage` null.

**4. Read models.**
- `BotOrchestratorRead.ai_cost_usd: float | None` (on list and detail).
- `OrchestratorRunSummaryRead` gains `usage` (object or null) and `ai_cost_usd`.
- Every list and detail endpoint computes its costs with at most one cost query for the
  orchestrators plus one for the runs page, and degrades to `None` throughout when the
  source is unavailable.
- `0.0` means reachable but no spend, mirroring the portfolio convention.

**5. Dashboard.**
- `DashboardAiCosts` gains `orchestrators: list[OrchestratorAiCost]` (`orchestrator_id`,
  `label`, `ai_cost_usd`) for active orchestrators.
- `total_ai_cost_usd` becomes the sum of readable portfolio and orchestrator costs, or
  `None` when nothing is readable.
- The API schema mirrors this.
- The frontend `AiCostBreakdown` merges both lists into one cost-descending table.
  Orchestrator rows carry a small "Orchestrator" tag and link to `/orchestrators/:id`.
- The empty state applies only when both lists are empty.

## Risks / Trade-offs

- [The per-orchestrator total depends on run ids, so deleting runs would drop their
  cost] → runs are never deleted (orchestrators only stop and archive).
- [A very old, very active orchestrator makes the `ANY(:ids)` list long] → about 250
  ids a year is trivial for Postgres; revisit with a trace-id prefix query if ever needed.
- [Usage counts only the final agent run; web-search tool calls cost nothing in LLM
  tokens beyond the turns the SDK already counts] → the SDK's usage covers every model
  request in the run, which is what we want.

## Migration Plan

One Alembic revision adds the nullable `bot_orchestrator_runs.usage` JSONB column (no
backfill; earlier runs show no tokens but still show cost). The backend container applies
it on start; deploy with `docker compose up -d --build` so the new migration file is in
the image. Rollback drops the column.
