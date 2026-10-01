## Why

The agents' `web_search` tool is hard-wired to SerpAPI. The user has a more
generous free-search allowance on Serper (serper.dev) and wants to use it, but
without losing the existing SerpAPI path. Making the provider a configuration
choice lets either backend be selected per deployment without code changes.

## What Changes

- Add a `WEB_SEARCH_PROVIDER` setting (`serpapi` | `serper`, default `serpapi`
  so existing deployments are unaffected) that selects which backend the
  `web_search` tool calls.
- Add a Serper implementation (POST to `https://google.serper.dev/search` with
  an `X-API-KEY` header) alongside the existing SerpAPI SDK implementation. Both
  remain available; selection is runtime config.
- Add a `SERPER_API_KEY` setting for the Serper key; keep `SERP_API_KEY` for
  SerpAPI. Each provider errors clearly when its own key is missing; an
  unrecognised provider value errors clearly.
- Both providers normalise their raw responses to the **same** trimmed result
  shape the tool already emits (top organic results as `{title, link, snippet}`
  plus any answer-box / knowledge-graph snippet), so the stored research
  transcript and the UI that renders it are unaffected.
- The provider-agnostic machinery is unchanged: the per-run web-search budget
  cap, the research-log capture, the timeout wrapper, and the result count.
- Document `WEB_SEARCH_PROVIDER` and `SERPER_API_KEY` in `.env.example`,
  `docker-compose.yml`, and the README.

## Capabilities

### New Capabilities

- `web-search`: the agents' configurable web-search tool — a provider-selectable
  backend (SerpAPI or Serper) that returns a normalised, budget-capped, trimmed
  result set to the recommender and AI-portfolio agents.

### Modified Capabilities

<!-- None. The web-search tool's behaviour was never captured as its own spec
     requirement; this change introduces it as a new capability. The recommender
     and AI-portfolio specs reference "web search" only in prose and keep their
     existing observable behaviour unchanged. -->

## Impact

- Code: `backend/src/cadence/agents/tools.py` (provider dispatch + Serper impl +
  response normalisation), `backend/src/cadence/config.py` (two settings).
- Config/ops: `.env.example`, `docker-compose.yml`, `README.md`.
- Dependencies: no new dependency (SerpAPI SDK kept; Serper uses the existing
  `httpx`).
- No DB migration. No API schema change. No frontend change (the research
  transcript shape is preserved).
- Tests: `tests/test_agents_tools.py`, `tests/test_ai_portfolio_agent.py`.
