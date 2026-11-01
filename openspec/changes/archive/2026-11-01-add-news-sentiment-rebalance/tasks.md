## 1. Sentiment scoring service (sidecar)

- [ ] 1.1 Create the `sentiment-service` (FastAPI + ONNX Runtime int8, pinned FinBERT artifact baked into the image) exposing a scoring endpoint (text[] → per-text pos/neu/neg probabilities) and a `/health` endpoint that warm-loads the model at startup and only reports healthy once it can score; verify a local run scores a sample headline and `/health` gates on model load
- [x] 1.2 Add the `sentiment-service` to docker-compose with a conservative `mem_limit` and a healthcheck wired to `/health`; verify the compose config references the service and the backend depends on it being healthy

## 2. Backend sentiment package and contracts

- [x] 2.1 Create the `news_sentiment` package (`models.py`, `service.py`, `errors.py`, `constants.py`); verify `uv run mypy src/cadence` passes on the new package
- [x] 2.2 Define the `SentimentScorer` Protocol (`@runtime_checkable`) plus a real HTTP client and an injectable stub, and a news-source Protocol (Alpaca News / Benzinga) with a stub; verify unit tests assert the stub satisfies the Protocol and the client degrades (no raise) when the service URL is unset or unreachable
- [x] 2.3 Add Pydantic settings: `SENTIMENT_SERVICE_URL` (empty ⇒ feature disabled), trailing-window length (default ~3 days), recency-weighting/neutral-band knobs; verify a unit test reads the defaults and that an empty URL marks the feature disabled
- [x] 2.4 Implement the trailing-window recency-weighted aggregate `(p_pos − p_neg)` + article count with a deterministic positive/neutral/negative classification, cached per `(ticker, date)`; verify unit tests for the weighting, the classification bands, determinism, and cache reuse
- [x] 2.5 Implement the graceful-degradation contract (unset URL, unreachable, scoring error, or no news → explicit per-ticker "sentiment unavailable", never raise); verify unit tests for each degradation path and a partial-availability batch

## 3. Rebalance prompt integration

- [x] 3.1 Add `SENTIMENT_PROMPT_VERSION` and a seed Alembic migration inserting the sentiment-aware rebalance prompt (prior version's text verbatim + a defensive per-ticker sentiment block section describing it long-only and tolerating absence); verify the migration round-trips and the seeded template differs from the prior version only by the sentiment section
- [x] 3.2 Add the `paper_trading_sessions.use_news_sentiment` column migration (non-nullable, default off, down_revision = current head); verify upgrade/downgrade round-trips against the test DB
- [x] 3.3 Thread `use_news_sentiment` through `AIBuildParams` → `create_session` → the session row (build flow persists the flag only, attaches nothing); verify a unit test that a built session records the chosen flag and is frozen
- [x] 3.4 In `flows/rebalance.py`, attach the per-ticker sentiment block to both candidates and holdings, gated on `use_news_sentiment` AND frozen version ≥ `SENTIMENT_PROMPT_VERSION`, marking unavailable tickers; verify unit tests: opted-in on sentiment-aware version attaches to candidates + holdings; opted-out attaches nothing; older frozen version attaches nothing; unavailable sentiment marked not fabricated; rebalance proceeds when the service is down
- [x] 3.5 Confirm the routed initial allocation inherits sentiment with no extra wiring (it runs as a rebalance); verify a unit test that an opted-in session's initial allocation attaches the sentiment block

## 4. Read model and schemas

- [x] 4.1 Add `use_news_sentiment` to `PaperTradingSessionRead` (and the build request schema) with explicit router mapping; verify `model_validate` maps the flag and a router test returns it on list and single-session reads
- [x] 4.2 Verify `uv run mypy src/cadence` passes on the schema/router changes

## 5. Frontend

- [x] 5.1 Add `use_news_sentiment` to the TS `AIPortfolioBuildRequest` and `PaperTradingSessionRead` mirrors; verify `npm run typecheck` passes
- [x] 5.2 Add the "Use news sentiment" toggle (default off) to `BuildAIPortfolioCard`; verify vitest asserts it defaults off and is sent with the build request when enabled and when left off
- [x] 5.3 Add a session-detail "News sentiment" fact tile mirroring the fundamentals tile; verify vitest asserts it reflects the session's flag

## 6. Verification

- [x] 6.1 Run backend gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` — all green
- [x] 6.2 Run frontend gates: `cd frontend && npm run typecheck && npm run test && npm run build` — all green
- [x] 6.3 Run `openspec validate add-news-sentiment-rebalance --strict` — valid
