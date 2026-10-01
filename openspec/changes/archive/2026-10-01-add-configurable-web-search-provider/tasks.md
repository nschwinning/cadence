## 1. Config

- [x] 1.1 In `backend/src/cadence/config.py` add `WEB_SEARCH_PROVIDER: str = "serpapi"` (documented as `serpapi` | `serper`) and `SERPER_API_KEY: str = ""` alongside the existing `SERP_API_KEY`.

## 2. Provider dispatch + Serper implementation

- [x] 2.1 In `backend/src/cadence/agents/tools.py`, extract the current SerpAPI call into `_search_serpapi(query) -> dict` (SDK call + `_trim_serp_payload`), raising a clear `ValueError` when `SERP_API_KEY` is unset (preserve today's message).
- [x] 2.2 Add `_search_serper(query) -> dict`: POST `https://google.serper.dev/search` via `httpx` with header `X-API-KEY: SERPER_API_KEY` and JSON body `{"q": query, "num": MAX_ORGANIC_RESULTS, "gl": "us", "hl": "en"}` (synchronous call, so it runs under the existing executor + `asyncio.wait_for` timeout); raise a clear `ValueError` when `SERPER_API_KEY` is unset; convert a non-200 / request error into a `{"error": ...}` result.
- [x] 2.3 Add `_trim_serper_payload(raw) -> dict` mapping Serper's keys (`organic` → `organic_results`, `answerBox` → `answer_box`, `knowledgeGraph` → `knowledge_graph`) into the SAME trimmed shape `_trim_serp_payload` emits (capped `MAX_ORGANIC_RESULTS` organic items as `{title, link, snippet}`, compacted answer-box and knowledge-graph, pass-through `error`).
- [x] 2.4 Update `_run_web_search` to dispatch on `settings.WEB_SEARCH_PROVIDER` to `_search_serpapi` / `_search_serper` after the budget check, raising a clear `ValueError` for an unrecognised provider value; keep the budget decrement, off-thread executor + timeout wrapper, and `note_web_search` recording wrapping both providers unchanged.
- [x] 2.5 Update the `web_search` tool description and module/docstrings to describe it as provider-configurable (SerpAPI or Serper) rather than SerpAPI-only.

## 3. Config / ops / docs

- [x] 3.1 Add `WEB_SEARCH_PROVIDER` and `SERPER_API_KEY` to `.env.example` (document default + accepted values) and forward `SERPER_API_KEY` / `WEB_SEARCH_PROVIDER` in `docker-compose.yml` next to `SERP_API_KEY`.
- [x] 3.2 Update `README.md` to document `WEB_SEARCH_PROVIDER` + `SERPER_API_KEY` alongside `SERP_API_KEY`.

## 4. Tests

- [x] 4.1 In `tests/test_agents_tools.py`, keep the existing SerpAPI `_trim_serp_payload` assertions and add `_trim_serper_payload` tests proving a representative Serper payload (keys `organic`/`answerBox`/`knowledgeGraph`) normalises to the shared shape and surfaces an error field.
- [x] 4.2 In `tests/test_ai_portfolio_agent.py`, pin the existing budget tests to `WEB_SEARCH_PROVIDER=serpapi` (monkeypatch), and add Serper-path tests: monkeypatch the `httpx` POST, assert the Serper branch is used and normalises results; assert a missing `SERPER_API_KEY` raises the provider-named error; assert an unrecognised `WEB_SEARCH_PROVIDER` raises a clear error; assert the budget cap still short-circuits before the provider under Serper.

## 5. Verification

- [x] 5.1 Run `uv run ruff check . && uv run mypy src/cadence && uv run pytest` and verify the full backend suite is green.
- [x] 5.2 Run `openspec validate add-configurable-web-search-provider --strict` and verify it passes.
