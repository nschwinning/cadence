# Cadence

Cadence is an AI paper-trading application. It combines a Quantara-style asset
universe (managed asset list with metadata), an AI asset recommender, and an AI
portfolio manager that runs paper trades through **Alpaca** with a **daily
rebalance**.

This repository is the project skeleton: it boots, serves a health endpoint, and
carries the shared infrastructure. The trading features are layered on in later
phases.

## Tech stack

- **Backend**: FastAPI, Pydantic v2, SQLAlchemy 2.0 (typed ORM), Alembic
  migrations, PostgreSQL, `uv`-managed Python 3.12. AI via the `openai-agents`
  SDK; market/broker access via Alpaca.
- **Frontend**: React 19 + TypeScript, Vite, TanStack Query, React Router,
  Tailwind CSS, Vitest + React Testing Library.
- **Infra**: Docker Compose (Postgres, backend, frontend, and a cron sidecar for
  the daily rebalance trigger).

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

## Environment variables

Configured via the root `.env` (see `.env.example`):

- `DATABASE_URL`, `TEST_DATABASE_URL`, `CORS_ORIGINS`
- AI recommender: `OPENAI_API_KEY`, `SERP_API_KEY`, `RECOMMENDER_MODEL`,
  `RECOMMENDER_STUB`
- AI portfolio / Alpaca: `AI_PORTFOLIO_MODEL`, `ALPACA_API_KEY`,
  `ALPACA_SECRET_KEY`, `ALPACA_PAPER`, `ALPACA_STUB`
- Daily rebalance trigger: `REBALANCE_CRON_TOKEN` (plus `CRON_TZ` /
  `REBALANCE_SCHEDULE` for the cron sidecar)
