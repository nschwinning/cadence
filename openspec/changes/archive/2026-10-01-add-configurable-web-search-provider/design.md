## Context

The web-search integration is isolated to `backend/src/cadence/agents/tools.py`.
Today `_run_web_search` calls the SerpAPI SDK (`serpapi.Client(api_key=...)
.search({...}).as_dict()`) and `_trim_serp_payload` reduces the raw payload to
`{error?, organic_results[{title,link,snippet}], answer_box{...}?,
knowledge_graph{...}?}`. That trimmed dict is both returned to the agent and
recorded via `note_web_search` into the run's research log, persisted on
`AIPortfolioEvent.research` (JSONB) and rendered by the frontend `ResearchCard`.
The budget cap (`web_search_budget` ContextVar fed by
`AI_PORTFOLIO_MAX_WEB_SEARCHES`), the research-log capture, the off-thread
`asyncio.wait_for(..., SEARCH_TIMEOUT_SECONDS)` wrapper, and `MAX_ORGANIC_RESULTS`
all sit above the provider call and are provider-agnostic.

## Goals / Non-Goals

**Goals:**
- Select the search backend by config, keeping SerpAPI and adding Serper.
- Keep the trimmed result shape identical across providers so persistence and
  the UI need no change.
- Keep budget, timeout, and research-logging behaviour exactly as-is.

**Non-Goals:**
- No change to the research transcript schema, the API, or the frontend.
- No new provider abstraction beyond what two backends need (no plugin
  registry); adding a third provider later is a small follow-up.
- Not removing SerpAPI — both stay shipped.

## Decisions

- **Dispatch inside `_run_web_search`, not a class hierarchy.** After the budget
  check, branch on `settings.WEB_SEARCH_PROVIDER` to `_search_serpapi(query)` or
  `_search_serper(query)`; everything else (budget decrement, timeout wrapper,
  `note_web_search`) stays in `_run_web_search` and wraps both. Two small module
  functions are simpler than a Protocol + registry for exactly two providers and
  keep the shared machinery in one place. An unknown provider value raises
  `ValueError` before any network call.
- **Normalise at the provider boundary.** `_search_serpapi` keeps the current
  SDK call + `_trim_serp_payload`. `_search_serper` POSTs to
  `https://google.serper.dev/search` with header `X-API-KEY` and body
  `{"q": query, "num": MAX_ORGANIC_RESULTS, "gl": "us", "hl": "en"}`, then a new
  `_trim_serper_payload` maps Serper's keys (`organic` → `organic_results`,
  `answerBox` → `answer_box`, `knowledgeGraph` → `knowledge_graph`) into the
  **same** trimmed shape `_trim_serp_payload` produces. This is the crux: a
  single normalised shape means the research log, JSONB column, and `ResearchCard`
  are untouched. A Serper HTTP error/non-200 is converted to `{"error": "..."}`
  mirroring how SerpAPI errors surface, so the agent sees a uniform error field.
- **Serper transport: `httpx` (already a dependency).** The existing SerpAPI call
  runs the blocking SDK in an executor under a timeout; `_search_serper` uses a
  synchronous `httpx.post(..., timeout=SEARCH_TIMEOUT_SECONDS)` run in that same
  executor path so the existing `asyncio.wait_for` wrapper and timeout semantics
  are unchanged. No new dependency; `serpapi` stays in `pyproject.toml`.
- **Two keys, default provider `serpapi`.** `SERP_API_KEY` stays; add
  `SERPER_API_KEY`. `WEB_SEARCH_PROVIDER` defaults to `"serpapi"` so existing
  deployments behave identically until they opt in. Each provider function
  raises a clear `ValueError` naming its own missing key, matching today's
  `SERP_API_KEY is not set` guard.

## Risks / Trade-offs

- **Serper response schema drift** (its keys differ from SerpAPI) → isolate all
  Serper-specific key handling in `_trim_serper_payload`; unit-test the mapping
  against a representative Serper payload so a mismatch fails fast.
- **Divergent error formats between providers** → both funnel into the same
  `{"error": ...}` field; test that a Serper non-200 / missing-key path yields an
  error result, not an exception to the agent.
- **Default stays SerpAPI, so the user must set two env vars to actually switch**
  → documented explicitly in `.env.example`, `docker-compose.yml`, and the
  README; called out in the apply summary.

## Migration Plan

No DB migration. Deploy is config-only: to use Serper, set
`WEB_SEARCH_PROVIDER=serper` and `SERPER_API_KEY=...`. Rollback is setting
`WEB_SEARCH_PROVIDER=serpapi` (or unsetting it, since that is the default).
