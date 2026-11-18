## Why

Upcoming work (Keycloak auth behind a Caddy reverse proxy) needs testing on the real Pi without
touching the Alpaca paper account the QA deployment trades on. A **DEV** environment running next to
QA on the Pi, with Alpaca fully mocked and real (low-budget) AI keys, gives a safe place to try
changes end to end.

## What Changes

- **Everything Alpaca honours the stub**: news headlines / news sentiment now also return no news
  without a network call when `ALPACA_STUB` is on (broker, bot bars and the system-status probe
  already do).
- **`mock` account mode**: a stubbed deployment reports configured and verified mode `mock`
  (instead of presenting the stub as a paper account); the header badge shows `DEV · Mock` in blue,
  distinct from paper (grey), live (red) and blocked (amber).
- **Side-by-side deployments**: the four published ports become configurable — `DB_HOST_PORT`
  (5435), `LITELLM_HOST_PORT` (4000), `BACKEND_HOST_PORT` (8002), `FRONTEND_HOST_PORT` (5174);
  defaults unchanged, so QA is unaffected. Compose already isolates volumes and networks per
  project name.
- **`.env.dev.example`**: `CADENCE_ENVIRONMENT=DEV`, `ALPACA_STUB=true`, no Alpaca keys, DEV ports
  (e.g. 5436 / 4001 / 8003 / 5175), a note to use a separate low-limit OpenAI / LiteLLM budget, and
  the daily AI schedules parked so DEV only spends when you run something by hand.
- **`docs/environments.md`**: the three-environment plan (DEV → QA → PRD), one checkout per
  environment (each directory is its own compose project), first-time setup, updates and promotion
  between environments, and the prerequisites before PRD may trade real money.
- No migration, no deployment scripts.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `deployment-environment`: `mock` account mode and badge; fully mocked brokerage; side-by-side
  deployments.

## Impact

- Backend: `news_sentiment/news.py` (stub short-circuit), `broker/models.py` (`AccountMode` gains
  `mock`), `broker/stub.py`, `environment.py`, `api/schemas.py`.
- Frontend: `types/api.ts`, `components/layout/EnvironmentBadge.tsx`.
- Deploy config: `docker-compose.yml` (port variables), `.env.dev.example`, `docs/environments.md`.
- The Keycloak change follows and adds Caddy; its ports will be configurable the same way.
