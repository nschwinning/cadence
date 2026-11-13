## 1. Search results

- [x] 1.1 `agents/tools.py`: keep organic `date` and up to 5 `top_stories` (title, link, source, date) for SerpAPI and Serper; verify with pytest (both providers map to the same shape; absent blocks omitted; existing shape unchanged otherwise).

## 2. Headlines

- [x] 2.1 Settings `NEWS_HEADLINES_PER_TICKER` / `NEWS_HEADLINES_WINDOW_DAYS` (+ `.env.example`, `docker-compose.yml`).
- [x] 2.2 `news_sentiment/news.py` `recent_headlines(...)` (bounded concurrency, crypto symbol form, never raises, omits empty tickers, 0 disables); verify with pytest using a fake source.
- [x] 2.3 Rebalance flows (stock + crypto) attach `recent_headlines` to holdings and candidates for every session; verify with pytest (session without news sentiment gets headlines; fetch failure → no field, run proceeds; disabled → none).

## 3. Run context

- [x] 3.1 `ai_portfolio/agent.py` `_run_context_block` appended to every rebalance input (stock + crypto, any frozen version); verify with pytest (date present, guidance present, appended after guardrails / outcomes).
- [x] 3.2 Orchestrator instructions gain the research guidance; `ORCHESTRATOR_PROMPT_VERSION` 3; verify with the agent tests.

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 `openspec validate add-recent-news-awareness --strict` passes.
