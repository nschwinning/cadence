## 1. Backend

- [x] 1.1 `AlpacaNewsSource.fetch_news` returns `[]` without a request when `ALPACA_STUB`; verify with pytest (keys set + stub → no HTTP call, empty result).
- [x] 1.2 `AccountMode` gains `mock`; `configured_mode()` and `StubBroker.probe_account_mode()` return `mock` under the stub; schema literal; verify with pytest (stub → DEV/mock/no mismatch/trading enabled; endpoint).

## 2. Frontend

- [x] 2.1 `AccountMode` type + blue `DEV · Mock` badge; verify with vitest.

## 3. Deploy config & docs

- [x] 3.1 Configurable published ports in `docker-compose.yml` (defaults unchanged); verify `docker compose config` renders the defaults and the DEV values.
- [x] 3.2 `.env.dev.example` and `docs/environments.md`.

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 `openspec validate add-dev-environment --strict` passes.
