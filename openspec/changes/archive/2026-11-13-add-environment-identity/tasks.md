## 1. Backend

- [x] 1.1 Settings `CADENCE_ENVIRONMENT` / `ALPACA_ALLOW_LIVE`; `docker-compose.yml` + `.env.example`; verify with a settings default test.
- [x] 1.2 `Broker.probe_account_mode` — Alpaca (configured endpoint, fallback to the other on 401/403, `unknown` otherwise) and stub (`paper`); verify with pytest using a faked HTTP layer (paper ok; live keys on paper config → live; both rejected → unknown; network error → unknown; never a write).
- [x] 1.3 `cadence/environment.py` resolver with TTL cache + `ensure_trading_allowed`; verify with pytest (match / mismatch / live without and with opt-in / unknown; cache hit and expiry).
- [x] 1.4 Guard in `OrderGateway` before the journal intent (`TradingDisabledError`); verify with pytest (refused order journals nothing and calls no submit; a bot tick records the failure; allowed path unchanged).
- [x] 1.5 `GET /api/v1/system/environment` + schema; verify with an API test (fields, no secrets).

## 2. Frontend

- [x] 2.1 `useEnvironment` hook + types; header badge variants (paper, live, mismatch, live-disabled, unknown) with tooltip; verify with vitest.

## 3. Verification

- [x] 3.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 3.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 3.3 `openspec validate add-environment-identity --strict` passes.
