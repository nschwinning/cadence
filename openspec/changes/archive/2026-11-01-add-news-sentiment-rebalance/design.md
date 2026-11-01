## Context

The AI paper-trading rebalance agent reasons over price, technical indicators,
fundamentals, learning feedback, and its own prompt. It has no view of **news tone**.
Kirtac & Germano (2024) show transformer sentiment on financial news is a tradeable
signal in a long-only regime (OPT Sharpe ≈1.81, 74.4% directional accuracy vs 50.1%
for the LM dictionary). We want to feed that signal into the *existing* stack as a
per-session opt-in, without disturbing the long-only output contract, the executor,
valuation, or guardrails. The established precedent is the **company-fundamentals**
opt-in: a build-time-frozen flag, a new rebalance prompt version, and a per-ticker
block attached to candidates and holdings with a defensive prompt and an explicit
"unavailable" marker. This change mirrors that precedent exactly and adds one new
piece: the scorer is heavy (a transformer), so it lives **out of process**.

## Goals / Non-Goals

**Goals (v1)**
- Opt-in per-session `use_news_sentiment` flag, default off, frozen at build,
  honored on rebalance (including the routed initial allocation) when the frozen
  prompt version ≥ the sentiment-aware version.
- A per-ticker advisory sentiment block on candidates and holdings; explicit
  "sentiment unavailable" marker; defensive prompt; long-only contract preserved.
- A separate **sentiment-scoring service** (FinBERT via ONNX Runtime int8) reached
  behind a `SentimentScorer` Protocol (real HTTP client + stub).
- News from the Alpaca News API (Benzinga); trailing ~3-day recency-weighted tone
  aggregate + article count, cached per `(ticker, date)`.
- Graceful degradation: unconfigured/unreachable/erroring/no-news → "unavailable",
  never a failed rebalance.
- Surfaced: build-form toggle (default off) + session-detail fact tile.

**Non-Goals (v1)**
- Shorting / long-short (the paper's 355% headline regime). Negative tone only
  avoids/trims. Long-short is a separate track touching executor/valuation/guardrails.
- A deterministic weight tilt — the signal is advisory prompt input only.
- Changing the AI output schema, the executor, valuation, guardrails, or rebalance
  scheduling.
- Fine-tuning the model, labeling by forward returns, or scoring anything beyond
  tone (the paper's OPT fine-tune is out of scope; we score tone).
- Backfilling sentiment history; attaching sentiment on the (dead) build prompt path.

## Decisions

### Separate scoring service behind a `SentimentScorer` Protocol
A transformer in-process would add torch (~200MB+) to the backend image and compete
for RAM on the Raspberry Pi. Instead a **`sentiment-service`** container (FastAPI +
ONNX Runtime int8, a pinned FinBERT artifact baked into the image, warm-loaded at
startup, `/health` gate) does the scoring. The backend depends only on a
`SentimentScorer` **Protocol** — a thin HTTP client for real runs, a deterministic
stub for tests/offline — matching how `MarketDataProvider`, `Broker`, and
`RecommenderAgent` are isolated. `SENTIMENT_SERVICE_URL` empty ⇒ feature disabled
(universally "unavailable"), so nothing breaks when the sidecar is absent.

**Why FinBERT/ONNX int8:** paper-validated lineage (ProsusAI/finbert), supervised
3-class tone, ~110M params; int8 runtime ≈50MB and model ≈110MB with good aarch64
CPU wheels and no torch — Pi-friendly and deterministic. Default int8 + a
conservative `mem_limit` makes Pi RAM non-blocking.

### News source: Alpaca News (Benzinga)
Free on the paper plan, ticker-tagged, reuses existing Alpaca credentials — no new
vendor. Behind a provider seam with a stub. Trailing window default ~3 days
(configurable).

### Aggregation + cache
Per ticker: score each headline in the window to `(p_pos, p_neu, p_neg)`, reduce to
a **recency-weighted mean of `(p_pos − p_neg)`** plus the **article count**, and
classify to a positive/neutral/negative leaning for the prompt. Deterministic given
inputs. Cache keyed by `(ticker, date)` so a day's rebalance (and the initial
allocation that same day) reuse one scoring pass.

### Rebalance attachment mirrors fundamentals (REBALANCE-ONLY)
A new `SENTIMENT_PROMPT_VERSION`; a seed migration adds the sentiment-aware prompt
instructions (prior version's text verbatim + a defensive sentiment block section).
The attach happens only in the rebalance flow (`flows/rebalance.py`), on both
`_candidates_from_universe` and `_build_holdings`, gated by `use_news_sentiment` AND
frozen version ≥ `SENTIMENT_PROMPT_VERSION`. The build flow just persists the flag.
Because the opening allocation is now routed through an inline initial rebalance, it
inherits sentiment automatically — no separate wiring.

### Flag threading mirrors `use_fundamentals`
New non-nullable `paper_trading_sessions.use_news_sentiment` (column migration,
default off). Threaded through `AIBuildParams` → `create_session` → session row →
`PaperTradingSessionRead`, and surfaced on the build card + a session-detail fact
tile. No change to the AI output schema.

### Degradation contract
Any failure mode — unset URL, unreachable service, scoring error, no news — yields an
explicit per-ticker "sentiment unavailable" that the prompt renders as a marker. The
sentiment path is wrapped so it can never raise out of the rebalance flow (same
fail-open posture as fundamentals and the unexecutable-weight redeploy).

## Risks / Trade-offs

- **Signal quality vs the paper:** we score *tone* with FinBERT, not OPT's
  forward-return fine-tune; expect the long-only-enhancement regime (Sharpe ≈1.81),
  not the 355% long-short headline. Framed explicitly in the proposal so the result
  is judged against the right baseline.
- **Advisory, not enforced:** the agent may ignore the signal. Accepted — keeps the
  output contract and avoids a brittle deterministic tilt; revisit if the agent
  underweights it.
- **News coverage gaps** (thinly-covered tickers, crypto) surface as "unavailable"
  rather than noise — correct, not a bug.
- **Extra container on the Pi:** mitigated by ONNX int8 + `mem_limit`; the feature is
  off by default and fully degradable, so the sidecar is optional.
- **Latency per rebalance:** one batched scoring pass per ticker-day, cached; bounded
  and off the daily critical path for opted-out sessions.

## Migration Plan

Two additive Alembic migrations: (1) a **seed** migration inserting the
sentiment-aware rebalance prompt version (template identical to the prior version
plus the defensive sentiment section); (2) a **column** migration adding
`paper_trading_sessions.use_news_sentiment` (non-nullable, default off). No backfill;
existing sessions read as sentiment-disabled and behave unchanged. Rollback drops the
column and the seeded prompt row. The scoring service is additive infra
(docker-compose) with no schema.

## Open Questions

- Exact recency-weighting kernel (linear vs exponential decay) and the neutral-band
  thresholds for the positive/neutral/negative classification — finalize during apply
  with a deterministic default.
- Whether to cache scored headlines (per article id) in addition to the per-ticker-day
  aggregate, to share scoring across sessions on the same day. Proposed: start with
  the per-`(ticker, date)` aggregate cache; add article-level caching only if needed.
- Pinned FinBERT artifact distribution (baked into the image vs a volume) — proposed
  baked-in for reproducibility; revisit if image size on the Pi is a concern.
