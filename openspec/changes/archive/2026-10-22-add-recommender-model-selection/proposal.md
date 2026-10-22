## Why

The asset (universe) recommender and the watchlist recommender both run the same
shared `OpenAIRecommenderAgent`, which is hard-wired to `settings.RECOMMENDER_MODEL`
(`gpt-5-mini`): its agent is built without a `model` override, so every run uses
the configured default. Paper-trading sessions already let an operator pick a
model per session from a shared catalog, but recommendation runs cannot — there
is no way to try a stronger (or cheaper) model for a particular discovery run, or
to record which model produced a given set of candidates.

## What Changes

- A recommendation-run request MAY specify a `model` from the shared AI model
  catalog; when omitted it defaults to the configured `RECOMMENDER_MODEL`. An
  unknown model id is rejected (422) without creating a run.
- The selected model is persisted on the run and surfaced on the run read model,
  so every run records which model produced it. Existing runs are backfilled to
  the configured default.
- The chosen model is threaded through to the agent so the run actually executes
  on it (both the universe and watchlist targets, since they share the agent).
- The frontend recommend/watchlist run-create forms gain a model dropdown
  (reusing the existing model catalog), defaulting to the configured default, and
  the run detail/list surfaces the model each run used.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `asset-recommendations` — a recommendation run now selects and records its AI
  model (defaulting to the configured recommender model).
- `app-shell` — the recommend/watchlist run forms expose a model selector and the
  run surfaces the model it used.

## Impact

- Backend: `api/schemas.py`, `api/routers/recommendations.py`,
  `recommendations/background.py`, `recommendations/service.py`,
  `recommendations/agent.py`, `recommendations/models.py`,
  `recommendations/stub.py`, a new Alembic migration, and test fakes.
- Frontend: the recommend + watchlist run-create forms, the run detail/list
  display, TS types, and a co-located Vitest test.
- Out of scope: the separate universe-**evaluation** agent, per-model
  pricing/cost, and any change to when/how recommendations run.
