## Why

Kirtac & Germano (2024), *Sentiment trading with large language models* (Finance
Research Letters 62, 105227), show that classifying financial news headlines with a
transformer-grade model and trading on the resulting tone beats dictionary methods
by a wide margin — OPT reaches 74.4% directional accuracy versus 50.1% for the
Loughran-McDonald dictionary, and the long-only tone portfolio earns a Sharpe of
≈1.81. Cadence's AI paper-trading sessions currently rebalance on price, technical
indicators, fundamentals, and the model's own reasoning, but they are **blind to
news tone**. Adding an opt-in news-sentiment signal gives the rebalance agent a
cheap, paper-validated input: positive tone reinforces a buy/hold, negative tone
argues to avoid or trim — without changing the long-only contract.

We scope v1 to the **long-only enhancement regime** the paper reports (long-only
OPT Sharpe ≈1.81), not the long-short 355% headline, which would require shorting
the executor, valuation, and guardrails do not support today. The signal scores
**tone**, not a fine-tuned forward-return label, and is **advisory** — fed to the
agent's judgement, not applied as a deterministic weight tilt.

## What Changes

- A new **news-sentiment** capability: a standalone sentiment-scoring service
  (FinBERT served via ONNX Runtime int8, a pinned model artifact shipped in its
  image, warm-loaded at startup with a `/health` gate) that the backend reaches
  through a `SentimentScorer` **Protocol** — a real thin HTTP client plus an
  injectable stub for tests/offline. News comes from the **Alpaca News API**
  (Benzinga), reusing existing Alpaca credentials; a trailing ~3-day,
  recency-weighted aggregate of `(p_positive − p_negative)` plus article count is
  cached by `(ticker, date)`. An empty `SENTIMENT_SERVICE_URL` disables the feature,
  and any service/news error degrades gracefully to an explicit
  "sentiment unavailable" marker — never an error, never a fabricated score.

- **ai-paper-trading** (modified): a new per-session **`use_news_sentiment`** flag,
  default **off**, frozen at build, delivered as a new rebalance prompt version
  (bump `SENTIMENT_PROMPT_VERSION`). When a session opted in **and** is frozen on a
  prompt version at or after the sentiment-aware version, its rebalances attach a
  per-ticker **news-sentiment advisory block** to **both** the buy candidates and
  the current holdings; opted-out or older-version sessions behave exactly as
  before. Mirrors the existing company-fundamentals opt-in pattern, including the
  routed initial allocation (which runs as a rebalance). The session read model
  carries the new flag.

- **app-shell** (modified): a "Use news sentiment" toggle on the AI build form
  (defaults off) and a "News sentiment" fact tile on the session-detail page,
  mirroring the company-fundamentals toggle/tile.

## Capabilities

### New Capabilities
- `news-sentiment`: a sentiment-scoring service contract and news-sentiment signal —
  the FinBERT/ONNX scoring service behind a `SentimentScorer` Protocol, the Alpaca
  news source, trailing-window recency-weighted aggregation, per-`(ticker, date)`
  caching, and the graceful-degradation contract.

### Modified Capabilities
- `ai-paper-trading`: the rebalance prompt gains an opt-in per-ticker news-sentiment
  advisory block (new `use_news_sentiment` flag, new sentiment-aware prompt version),
  and the session read model carries the flag.
- `app-shell`: the AI build form gains a news-sentiment toggle (default off) and the
  session-detail view gains a news-sentiment fact tile.

## Impact

- **New service:** a `sentiment-service` container (FastAPI + ONNX Runtime int8 +
  pinned FinBERT artifact) added to docker-compose, deployed alongside the backend
  on the Raspberry Pi. No torch dependency; default int8 + a conservative
  `mem_limit` keep Pi RAM non-blocking.
- **Backend:** new `news_sentiment` package (`models`/`service`/`errors`/`constants`
  per convention) holding the `SentimentScorer` + news-source Protocols, the HTTP
  client, the stub, and the aggregation/cache logic; new settings
  (`SENTIMENT_SERVICE_URL`, window/weighting knobs); a new sentiment-aware rebalance
  prompt version seeded by migration; one column migration adding
  `paper_trading_sessions.use_news_sentiment`; threading through the rebalance flow,
  `AIBuildParams`, and `PaperTradingSessionRead`.
- **Frontend:** new build-card toggle + session-detail fact tile + the
  `AIPortfolioBuildRequest`/`PaperTradingSessionRead` type additions.
- **No change** to the AI output schema (long-only, weights ~1.0), the executor,
  valuation, guardrails, or when/how rebalances are scheduled.

## Assumptions (for review)

1. **Long-only in v1.** Negative sentiment is used to avoid/trim, never to short.
   Long-short is a separate, larger track (executor/valuation/guardrails).
2. **FinBERT (ProsusAI lineage), served as a separate ONNX-int8 microservice.**
   Chosen over an LLM-call scorer for cost/latency and over in-process torch for Pi
   footprint. Revisit if accuracy proves insufficient.
3. **Advisory, not a deterministic tilt.** The score is prompt input; the agent
   decides. We do not post-process weights by sentiment.
4. **Alpaca News (Benzinga) as the source.** Free on paper, ticker-tagged, reuses
   Alpaca creds. Coverage gaps surface as "sentiment unavailable".
5. **Pi RAM is non-blocking** at default int8 with a conservative `mem_limit`.
6. **Expectation framing:** targets the long-only enhancement regime (paper Sharpe
   ≈1.81), scoring tone — not the long-short 355% headline or a forward-return label.

## Sequencing with the other in-flight AI-signal changes

This change shares a seam with `add-price-ml-rebalance`: both add a per-session opt-in
flag, a **new rebalance prompt version**, and the same per-ticker attach points in
`flows/rebalance.py` (`_candidates_from_universe` and `_build_holdings`), plus the same
`AIBuildParams` / `PaperTradingSessionRead` / `BuildAIPortfolioCard` surfaces. They are
**not functionally dependent**, but they MUST be built **sequentially, not in parallel**,
to avoid colliding on the prompt-version number and conflicting mechanically in those
shared files.

Rebalance prompt versions are **linear and cumulative** (each version = the prior
version's text verbatim + one new block; each signal's attachment is independently gated
by `rebalance_prompt_version >= <its version>` AND its opt-in flag). Therefore
`SENTIMENT_PROMPT_VERSION` is **whatever the next free version is at apply time** — it is
deliberately left unpinned in this proposal. If `add-price-ml-rebalance` ships first (the
recommended order), that is version 4+1 → **6**, and this change's seed prompt SHALL be
the then-current head prompt (which already contains the price-ML section) verbatim + the
sentiment section. If this change ships first, it takes **5** and `add-price-ml-rebalance`
rebases to 6. A session frozen at an earlier version never gains a later signal — the
expected build-time-frozen behavior.
