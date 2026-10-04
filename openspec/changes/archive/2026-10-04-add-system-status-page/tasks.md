## 1. Backend: config + schemas

- [x] 1.1 Add a `SYSTEM_STATUS_PROBE_TIMEOUT_SECONDS: float` setting (small default, e.g. `5.0`) to `config.py`; verify it imports via `from cadence.config import settings` and reads an env override.
- [x] 1.2 Add `BackendStatusRead` and `SystemStatusRead` Pydantic models to `api/schemas.py` under a new "System status" banner: `BackendStatusRead { name: str, configured: bool, identifier: str | None, reachable: bool | None, latency_ms: float | None, detail: str | None }` and `SystemStatusRead { backends: list[BackendStatusRead] }`; verify `uv run mypy src/cadence` is clean.

## 2. Backend: probe service

- [x] 2.1 Create package `backend/src/cadence/system/` (`__init__.py`) and `system/service.py` with an internal probe-result dataclass and one probe function per backend, each returning the result and never raising (wrap in try/except → `reachable=False` + classified `detail`). Verify the module imports.
- [x] 2.2 Implement the Alpaca probe: when `settings.ALPACA_STUB` report `identifier="stub"`, `configured=True`, `reachable=None`, no network; else `configured = bool(ALPACA_API_KEY and ALPACA_SECRET_KEY)`, `identifier = "live"|"paper"` from `ALPACA_PAPER`, and when configured construct `AlpacaBroker()` inside try/except and call `get_clock()`, timing it. Verify a unit test with stub mode makes no network call and a test with blank creds reports `configured=False`, `reachable=None`.
- [x] 2.3 Implement the web-search probe: `identifier = settings.WEB_SEARCH_PROVIDER`; `configured` = the active provider's key present (`SERP_API_KEY` for serpapi, `SERPER_API_KEY` for serper); when configured run a minimal 1-result query via the existing web-search path and time it, treating a raised error or a payload containing `error` as unreachable. Verify a unit test (monkeypatching the provider call) reports reachable on success and unreachable on an `error` payload.
- [x] 2.4 Implement the yfinance probe: `configured=True` (no credential), `identifier="yfinance"`; probe via `MarketDataProvider.fetch_info("SPY")` and time it; empty/raised → unreachable. Verify a unit test using a fake provider reports reachable on data and unreachable on raise.
- [x] 2.5 Implement the OpenAI probe: `identifier = settings.AI_PORTFOLIO_MODEL`, `configured = bool(settings.OPENAI_API_KEY)`; when configured construct an `openai` client and call `models.retrieve(model)`, timing it, classifying auth vs not-found vs transport errors into `detail`; unconfigured → `reachable=None`. Verify a unit test (monkeypatching the client) reports reachable on success and unreachable with an auth detail on an auth error.
- [x] 2.6 Add `get_system_status() -> SystemStatusRead`-shaped aggregator in the service that runs all probes concurrently via a `ThreadPoolExecutor` with a per-future timeout of `SYSTEM_STATUS_PROBE_TIMEOUT_SECONDS`, converting a timed-out future into an unreachable entry with a timeout `detail`. Verify a unit test where one probe sleeps past the timeout still returns all backends with the slow one marked unreachable and the others intact.

## 3. Backend: router + wiring

- [x] 3.1 Create `api/routers/system.py` — thin `APIRouter(prefix="/system", tags=["system"])` with `GET /status` (not cron-guarded) calling the service and returning `SystemStatusRead`; register it in `api/routers/__init__.py` and mount it at `/api/v1` in `api/app.py`. Verify `GET /api/v1/system/status` returns 200 with a `backends` array.
- [x] 3.2 Add an API test (`tests/test_system_api.py`) asserting the endpoint returns 200 with an entry per backend even when a probe fails (patch one probe to raise/timeout), and asserting no secret value appears anywhere in the response body. Verify the test passes.

## 4. Frontend: client + types

- [x] 4.1 Add `SystemBackendStatus` and `SystemStatusResponse` interfaces to `src/types/api.ts` (mirroring the backend schemas) under a "System status" banner. Verify `npm run typecheck` is clean.
- [x] 4.2 Create `src/api/system.ts`: `systemKeys` query-key factory, raw `getSystemStatus()` hitting `/api/v1/system/status`, and `useSystemStatus()` (`useQuery` with a ~30s `refetchInterval`), exposing `refetch` for manual refresh. Verify a small vitest covering the raw fn (mocked axios) passes.

## 5. Frontend: page + navigation

- [x] 5.1 Create `src/pages/system/SystemStatusPage.tsx` mirroring `TechnicalIndicatorsPage.tsx`: a card per backend with a status pill (reachable=green / unreachable=red / unavailable-or-stub=slate), the identifier, configured flag, and latency; `isPending` loading state, `isError` alert state, and a "Refresh" button wired to `refetch`. Verify it renders each backend and never shows a secret.
- [x] 5.2 Add a "System" entry to `NAV_ITEMS` in `src/components/layout/Sidebar.tsx` with a new icon under `src/components/icons/`, and add `<Route path="system" element={<SystemStatusPage/>} />` in `src/App.tsx`. Verify the nav link renders, marks active, and routes to the page.
- [x] 5.3 Add/extend a Sidebar vitest to assert the "System" nav entry is present. Verify `npx vitest run` passes.

## 6. Verify

- [x] 6.1 From `backend/`: `uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
- [x] 6.2 From `frontend/`: `npm run typecheck && npx vitest run && npm run build`.
- [x] 6.3 `openspec validate add-system-status-page --strict`.
- [x] 6.4 Manual smoke (optional): with `ALPACA_STUB=true` and keys unset, `GET /api/v1/system/status` reports Alpaca mode "stub" (no network), web-search/OpenAI as not configured, and yfinance reachable; confirm no secret values appear in the payload.
