---
name: run-verify-app
description: Boot the Cadence stack locally — PostgreSQL, the FastAPI backend, and the Vite React frontend — and smoke-test a change end to end. Use to confirm a change works in the real app, not just in unit tests.
metadata:
  author: cadence
  version: "1.0"
---

Bring up the full stack and verify a change actually works end to end.

## Discover first
Don't assume commands — detect them:
- Look for `docker-compose.yml` / `compose.yaml`, a `Makefile`, `justfile`, `pyproject.toml`/`requirements.txt`, and `package.json` scripts.
- Identify how Postgres is provided (Docker, local service, or a test container) and how the backend reads its `DATABASE_URL`.

## Bring up the stack (adapt to what you find)
1. **Database:** start PostgreSQL (commonly `docker compose up -d db`). Confirm it accepts connections.
2. **Migrations:** apply schema — `alembic upgrade head`.
3. **Backend:** start FastAPI (commonly `uvicorn app.main:app --reload`). Run long-lived processes in the background so the session isn't blocked.
4. **Frontend:** start Vite (commonly `npm run dev`) in the background.

## Smoke-test
- Backend health/OpenAPI: `curl` the health route and `/docs` (or `/openapi.json`).
- Exercise the specific endpoint(s) the change touches with `curl`, checking status codes and payload shape.
- For UI changes, confirm the frontend serves and the relevant view loads without console/network errors; describe what to click if manual verification is needed.

## Report
- State exactly what came up, what you exercised, and the observed results (status codes, responses).
- If something failed, show the real error output — don't declare success on a partial bring-up.
- Tear down or leave running as the user prefers; note any background processes still alive.
