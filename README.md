# Cadence

Cadence is an AI paper-trading application. It combines a Quantara-style asset
universe (managed asset list with metadata), an AI asset recommender, and an AI
portfolio manager that runs paper trades through **Alpaca** with a **daily
rebalance**.

## What it does

- **Asset universe** — a managed list of stocks and crypto with metadata, market
  data, and SEC EDGAR fundamentals; an AI recommender proposes additions and a
  periodic AI evaluation reviews the universe.
- **AI paper-trading sessions** — build a portfolio and the AI runs it as paper
  trades on Alpaca with a daily rebalance (plus a weekend crypto-only rebalance).
  A build creates an empty shell; the opening allocation runs as the session's
  first rebalance, so every rebalance enhancement applies to it too.
- **Per-session configuration** — AI model (from a fixed catalog, for comparing
  models), technical indicators, company fundamentals, the price-ML signal, news
  sentiment, stop-loss, risk guardrails, and learning feedback are frozen at build
  time; benchmark and asset scope can be changed on a running session. Capital can be increased
  mid-session, with returns computed time-weighted so contributions don't distort
  performance.
- **Analytics** — value snapshots, time-weighted return, Sharpe, per-session and
  multi-session comparison charts, benchmark overlays, sector-performance
  breakdowns, per-portfolio AI (LLM) cost, and daily P&L reports via Pushover.
  Each AI run is recorded for per-run performance attribution.

## Tech stack

- **Backend**: FastAPI, Pydantic v2, SQLAlchemy 2.0 (typed ORM), Alembic
  migrations, PostgreSQL, `uv`-managed Python 3.12. AI via the `openai-agents`
  SDK, optionally routed through a **LiteLLM** model-gateway proxy whose
  spend logs back the per-portfolio AI cost view; market/broker access via Alpaca.
- **Frontend**: React 19 + TypeScript, Vite, TanStack Query, React Router,
  Tailwind CSS, Vitest + React Testing Library.
- **Infra**: Docker Compose (Postgres, backend, frontend, a cron sidecar for
  the daily rebalance trigger plus a weekend crypto-only rebalance, and a
  sentiment-scoring sidecar that serves FinBERT news-tone inference via ONNX
  Runtime, out-of-process so the backend stays lean).

## Ports

| Service   | Host port | Container port |
| --------- | --------- | -------------- |
| Postgres  | 5435      | 5432           |
| Backend   | 8002      | 8000           |
| Frontend  | 5174      | 5173           |

## Running

### Docker Compose (everything in containers)

```sh
cp .env.example .env   # adjust secrets as needed
docker compose up --build
```

- Backend: http://localhost:8002 (health at http://localhost:8002/health)
- Frontend: http://localhost:5174

### Host dev (backend + frontend on the host, Postgres in Docker)

Use this on machines behind a TLS-inspecting proxy so outbound HTTPS is verified
against the OS trust store:

```sh
./scripts/dev-host.sh
```

Trigger the daily rebalance manually against a host backend:

```sh
./scripts/run-rebalance.sh
```

Trigger the weekend crypto-only rebalance manually (rebalances just the crypto
sleeve of each session; equities stay frozen):

```sh
./scripts/run-crypto-rebalance.sh
```

## Environment variables

Configured via the root `.env` (see `.env.example`):

- `DATABASE_URL`, `TEST_DATABASE_URL`, `CORS_ORIGINS`
- AI recommender: `OPENAI_API_KEY`, `WEB_SEARCH_PROVIDER` (`serpapi` default |
  `serper`), `SERP_API_KEY`, `SERPER_API_KEY`, `RECOMMENDER_MODEL`,
  `RECOMMENDER_STUB`
- AI portfolio / Alpaca: `AI_PORTFOLIO_MODEL` (the default model for new
  sessions; each session freezes a model chosen from the fixed catalog at build
  time), `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER`, `ALPACA_STUB`
- AI gateway / cost tracking: `LITELLM_BASE_URL`, `LITELLM_API_KEY` (optional —
  route agent calls through a LiteLLM proxy; empty disables and calls go direct),
  `LITELLM_DATABASE_URL` (optional — the LiteLLM spend-log database that powers
  the dashboard's per-portfolio AI cost; empty hides the cost figures)
- Daily rebalance trigger: `REBALANCE_CRON_TOKEN` (plus `CRON_TZ` /
  `REBALANCE_SCHEDULE` for the cron sidecar)
- Weekend crypto-only rebalance: `CRYPTO_REBALANCE_SCHEDULE` (default
  `35 9 * * 6,0` — Sat/Sun just after the weekday open time; crypto trades 24/7,
  so the sidecar POSTs `/ai-portfolio/rebalance-crypto-daily` to rebalance each
  session's crypto sleeve while the US equity market is closed)
- End-of-day snapshot + P&L report: `SNAPSHOT_SCHEDULE` (default `15 16 * * *` —
  16:15 ET **every day, including weekends**; the sidecar POSTs
  `/ai-portfolio/snapshot-daily` to record each session's value snapshot and send
  its P&L report. Running on weekends captures weekend crypto moves in the NAV
  series so Saturdays/Sundays are not gaps)
- Quarterly fundamentals refresh: `FUNDAMENTALS_SCHEDULE` (default
  `0 6 1 1,4,7,10 *` — 06:00 ET on the 1st of Jan/Apr/Jul/Oct; the sidecar POSTs
  `/assets/fundamentals/refresh` to re-fetch SEC EDGAR fundamentals for **every
  stock asset** so stored figures track quarterly filings. New stocks also get
  fundamentals fetched on creation, so this job keeps existing stocks current).
  **One-time backfill:** after first deploying this job, invoke the endpoint once
  to populate stocks that predate it —
  `curl -fsS -X POST -H "X-Cron-Token: $REBALANCE_CRON_TOKEN" \
  http://<host>/api/v1/assets/fundamentals/refresh` (the same call the cron makes;
  re-running is safe — it re-fetches and upserts)
- Technical indicators: `INDICATORS_SCHEDULE` (default `0 5 * * 1-5` — 05:00 ET on
  weekdays; the sidecar POSTs `/technical-indicators/runs` to precompute technical
  indicators over the whole universe before the market-open rebalance so the trend
  gate reads fresh snapshots)
- Price-ML signal: `PRICE_ML_SCHEDULE` (default `30 5 * * 1-5` — 05:30 ET on
  weekdays; the sidecar POSTs `/price-ml/refresh` to run the nightly precompute
  over the whole universe **after** the technical-indicators run, training a
  pooled gradient-boosted classifier of each asset's forward-return sign and
  caching its direction signal). Tuning knobs read by the precompute and the
  rebalance-time annotation: `PRICE_ML_HORIZON_DAYS` (forward-return horizon in
  trading days, default `21`), `PRICE_ML_RETRAIN_DAYS` (retrain cadence, default
  `7`), `PRICE_ML_MIN_BAR_COUNT` (minimum stored daily bars to train/predict,
  default `260`), `PRICE_ML_STALENESS_DAYS` (signals older than this are rendered
  "unavailable", default `7`), `PRICE_ML_SEED` (deterministic-training seed,
  default `42`), `PRICE_ML_MODEL_VERSION` (schema version gating the cache,
  default `price-ml-v1`), and `PRICE_ML_MODEL_DIR` (cached model artifact
  directory, default `var/price_ml`)
- News sentiment: `SENTIMENT_SERVICE_URL` (base URL of the sentiment-scoring
  sidecar; **empty — the default — disables the feature entirely**, so every
  ticker degrades to "unavailable" and the signal is opt-in via deployment
  config. Docker Compose wires this to the `sentiment-service` container). Tuning
  knobs read at rebalance time for sessions opted into the signal:
  `SENTIMENT_SERVICE_TIMEOUT_SECONDS` (per-request timeout, default `10`),
  `SENTIMENT_WINDOW_DAYS` (trailing news window, default `3`),
  `SENTIMENT_RECENCY_HALFLIFE_DAYS` (recency weighting half-life, default `1.5`),
  `SENTIMENT_NEUTRAL_BAND` (neutral classification band around the weighted
  positive−negative aggregate, default `0.15`), `SENTIMENT_MAX_ARTICLES` (max news
  items scored per ticker per window, default `50`), and `ALPACA_NEWS_BASE_URL`
  (Alpaca News API source, reuses the Alpaca credentials)
