## Context

- `agents/tools.py`: `_trim_serp_payload` / `_trim_serper_payload` keep organic (title/link/snippet,
  max 5), answer box and knowledge graph. SerpAPI returns `top_stories` (title, link, source, date)
  and organic `date`; Serper returns `topStories` (title, link, source, date) and organic `date`.
- AI portfolio: each session freezes a DB-stored prompt version; data blocks attach by version +
  opt-in (fundamentals, price-ML, sentiment). `_build_rebalance_input` appends the guardrails and
  recent-outcomes sections to the rendered template independently of the version — the precedent
  used here.
- `news_sentiment/news.py`: `AlpacaNewsSource.fetch_news(ticker, start, limit)` (sort desc, never
  raises → `[]`) returns `NewsItem`s; `window_start(as_of, days)`.
- Orchestrator: `_AGENT_INSTRUCTIONS` in code, `ORCHESTRATOR_PROMPT_VERSION` 2; briefing has
  `as_of`.

User decisions: implement options 1 (headlines), 2 (top stories), 4 (date + guidance); headlines for
every portfolio, with or without news sentiment.

## Goals / Non-Goals

**Goals:** recent events reach the AI-portfolio agent through headlines and better search; both
agents research recency-aware.

**Non-Goals:** a dedicated news-search tool (option 3); headlines in the orchestrator briefing;
changing stored prompts or the sentiment score; showing headlines in the UI.

## Decisions

1. **Trimming**: organic entries add `date` when present; new `top_stories` list (≤ 5) of
   `{title, link, source, date}` (Serper `topStories` mapped to the same keys; nested `source`
   objects flattened to their name). Omitted when absent — existing results stay byte-identical.
2. **Headlines helper** (`news_sentiment/news.py`): `recent_headlines(tickers, *, as_of, per_ticker,
   window_days, source=None) -> dict[str, list[dict]]` — reuses the Alpaca source (`limit =
   per_ticker`), runs fetches on a small thread pool (max 8), returns only tickers with items, each
   `{headline, source, published_at}` (ISO). Crypto tickers are passed in Alpaca News form
   (`BTC-USD`/`BTC/USD` → `BTCUSD`). Never raises.
3. **Attaching** (rebalance flows, stock and crypto): resolve headlines once for holdings ∪
   candidates, then set `recent_headlines` on each candidate / holding dict that has some — after
   the existing blocks, so prompt ordering for other fields is unchanged.
4. **Run context** (`ai_portfolio/agent.py`): `_run_context_block(today)` appended last by
   `_build_rebalance_input` for every session (today from the market-tz clock seam already used by
   the flows). Wording:
   "Run context — today is {date} (US/Eastern). Research guidance: before keeping or adding a name,
   check for material developments of the last 7 days (management changes, investigations,
   guidance changes, mergers). Put the current month and year in news searches and prefer the
   `top_stories` block of search results. Check each result's date and disregard results older
   than the period you are assessing; company fiscal years differ from calendar years (e.g. a
   'fiscal 2026' quarter may have ended in 2025). Each holding and candidate may carry
   `recent_headlines` — the newest headlines with their dates."
5. **Orchestrator**: same guidance appended to `_AGENT_INSTRUCTIONS` (relative to the briefing's
   date); `ORCHESTRATOR_PROMPT_VERSION` 3.
6. **Settings**: `NEWS_HEADLINES_PER_TICKER: int = 3` (≥ 0), `NEWS_HEADLINES_WINDOW_DAYS: int = 3`;
   documented in `.env.example`, passed in `docker-compose.yml`.

## Risks / Trade-offs

- Existing sessions' inputs change despite frozen prompt versions — deliberate (same precedent as
  guardrails); their stored system prompt is untouched.
- Prompt growth: ~100 tickers × 3 headlines ≈ 30k characters (~7k tokens) on large universes;
  `NEWS_HEADLINES_PER_TICKER` tunes it.
- Alpaca News coverage for crypto is thinner; missing headlines just omit the field.

## Migration Plan

None. Takes effect on each portfolio's next rebalance and the next orchestrator run.

## Open Questions

None.
