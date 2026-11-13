## Why

When Nvidia's CEO resigned amid a scandal (Nov 12, 2026; the stock fell up to 14% at the open), an
AI-portfolio run researching NVDA saw none of it. Its search — "NVIDIA latest news 2026 earnings
guidance AI demand 2026 Nvidia Q3 2026 analysts outlook" — returned only earnings pages, mostly
about fiscal Q3 2026 (the quarter ended October 2025). Three gaps caused it:

1. The `web_search` tool keeps only the top 5 organic results plus answer box / knowledge graph; it
   **drops Google's "Top stories" block**, where breaking coverage appears, and it drops result
   dates.
2. The agent is **not told today's date** or how to research recent developments, so it writes
   evergreen queries and mistakes fiscal years for calendar years.
3. Recent **headlines never reach the agent**: news sentiment (when opted in) passes only a tone,
   score and article count, and portfolios without it get no news at all.

## What Changes

- **Search results keep news and dates**: the normalised result gains up to 5 `top_stories`
  (title, link, source, date) from SerpAPI `top_stories` / Serper `topStories`, and organic results
  keep their `date` when the provider supplies one. Applies to every agent using `web_search` (AI
  portfolios, orchestrator, recommendations).
- **Run context for every AI-portfolio rebalance** (stock and crypto prompts, every session,
  whatever its frozen prompt version — appended like the guardrails and recent-outcomes blocks):
  today's date (America/New_York) and research guidance — check the last 7 days for material
  developments before keeping or adding a name, put the current month and year in news searches,
  prefer `top_stories`, check every result's date, and remember fiscal years differ from calendar
  years.
- **Recent headlines for every portfolio** (by decision, with or without news sentiment): each
  holding and candidate carries `recent_headlines` — up to 3 newest headlines from the last 3 days,
  each with its date and source — fetched from Alpaca News with the existing keys (no scoring
  service needed). Missing news or a failed fetch simply omits the field; a run never fails on it.
  New settings `NEWS_HEADLINES_PER_TICKER` (default 3; 0 disables) and
  `NEWS_HEADLINES_WINDOW_DAYS` (default 3).
- **Orchestrator**: the same search improvements, plus the research guidance in its instructions
  (it already receives the date as `as_of`); prompt version 2 → 3. Headlines for the orchestrator's
  candidates are out of scope.
- No migration (no stored-prompt change), no frontend change.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `web-search`: trimmed results keep top stories and result dates.
- `ai-paper-trading`: every rebalance gets a run-context block and per-ticker recent headlines.
- `bot-orchestrator`: research guidance for recent developments.

## Impact

- Backend: `agents/tools.py` (trimming), `news_sentiment/news.py` (headline fetch helper reusing the
  Alpaca News source), `ai_portfolio/agent.py` (run-context block), `ai_portfolio/flows/rebalance.py`
  (+ crypto flow) attaching headlines, `bot_orchestrator/agent.py` (instructions, version 3),
  `config.py` (two settings).
- Behaviour change for **existing** portfolios: they receive the new block and headlines on their
  next rebalance even though their stored prompt version is frozen — deliberate, as for guardrails.
- Prompt size grows (roughly 2–8k input tokens per run depending on universe size; tunable via
  `NEWS_HEADLINES_PER_TICKER`), visible in each run's AI cost. One Alpaca News request per ticker
  per run (bounded concurrency).
