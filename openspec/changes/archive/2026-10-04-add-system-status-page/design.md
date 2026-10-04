## Context

See proposal.md — Why. Relevant current state (from the codebase):

- The only runtime status surface is `GET /health` (unprefixed, `api/routers/health.py`), which checks the DB only. All resource routers mount at `/api/v1` (`api/app.py`).
- External backends and how they are reached:
  - **Broker**: `broker/` package. `get_broker()` returns `StubBroker()` when `settings.ALPACA_STUB` else `AlpacaBroker()`. `AlpacaBroker.__init__` raises `broker.ConnectionError` when creds are blank, and `api/app.py` has a global `ConnectionError → 503` handler. `is_market_open()`/`get_clock()` hit `GET /v2/clock` — the cheapest authenticated probe (no market-data entitlement).
  - **Web search**: `agents/tools.py` dispatches on `settings.WEB_SEARCH_PROVIDER` (`serpapi` default | `serper`); each path reads its own key (`SERP_API_KEY` / `SERPER_API_KEY`) and raises `ValueError` when absent.
  - **Market data (yfinance)**: `assets/market_data.py` `YFinanceMarketDataProvider.fetch_info(ticker)`. No stub exists; the factory ignores stub flags.
  - **OpenAI**: the `openai-agents` SDK reads `OPENAI_API_KEY` from the environment implicitly; `settings.AI_PORTFOLIO_MODEL` / `RECOMMENDER_MODEL` name the models. No explicit client is constructed anywhere and there is no reachability helper. The `openai` package is available transitively.
- Backend conventions: thin router → service; shared `api/schemas.py`; `settings` singleton. The `technical_indicators.py` `/config` endpoint is the closest precedent for a plain read-only GET.
- Frontend conventions: data-driven `NAV_ITEMS` in `Sidebar.tsx`; routes in `App.tsx`; per-resource client (query-key factory + raw fn + TanStack hook) + `types/api.ts` mirror; `TechnicalIndicatorsPage.tsx` is the structural template (SectionCard, pending/error/data states).

## Goals / Non-Goals

**Goals:**
- One on-demand endpoint + page that answers "is each backend configured and reachable, and how fast" — accurate, isolated per backend, and bounded in time.
- Reuse the existing broker / provider / web-search seams rather than re-implementing their transport.
- Expose zero secrets.

**Non-Goals:**
- No persistence, history, or trend of status over time (no DB, no migration).
- No alerting, no auto-remediation, no authentication/role model (the app has none today; "admin" here means an informational page, not an access-controlled one).
- No change to how builds/rebalances/recommendations consume these backends; the probe code is diagnostic-only and separate from the hot paths.
- Not probing the database (that is what `/health` already covers).

## Decisions

### D1 — A dedicated `system` backend package + `system-status` capability
Put the probe logic in a new `backend/src/cadence/system/service.py` with one probe function per backend, each returning a small result object (`name`, `configured`, `identifier` fields, `reachable: bool | None`, `latency_ms: float | None`, `detail: str | None`). A thin `api/routers/system.py` exposes `GET /api/v1/system/status` returning `SystemStatusRead { backends: [BackendStatusRead] }`. Rationale: matches the package-per-capability convention; keeps diagnostic code out of the broker/provider modules. Alternative (extend `/health`): rejected — `/health` is an unprefixed liveness check that must stay cheap and always-200 for orchestration; mixing in slow outbound probes would change its contract.

### D2 — Probe strategy per backend (cheapest call that proves connectivity)
- **Alpaca**: if `ALPACA_STUB` → report `mode="stub"`, `configured=true`, `reachable=None` (no network). Else construct `AlpacaBroker()` **inside a try/except** (so the global 503 handler never fires), report `mode = "live"|"paper"` from `ALPACA_PAPER` and `configured = bool(key and secret)`; if configured, call `get_clock()` and time it.
- **Web search**: `provider = WEB_SEARCH_PROVIDER`; `configured = bool(SERP_API_KEY or SERPER_API_KEY)` for the active provider; if configured, run a minimal 1-result query via the existing `_run_web_search`/provider function and time it. Serper returns `{"error": ...}` rather than raising — treat a payload containing `error` as unreachable.
- **yfinance**: always `configured=true` (no key); probe `fetch_info("SPY")` and time it; empty/raised → unreachable.
- **OpenAI**: `model = AI_PORTFOLIO_MODEL`; `configured = bool(OPENAI_API_KEY)`; if configured, construct an `openai` client and call `models.retrieve(model)` (validates key + model id without a completion) and time it.

Rationale: each is the lowest-cost call that actually exercises the credential/endpoint. `models.retrieve` avoids paying for a completion while still catching a bad key or a wrong model name — the two most common misconfigurations.

### D3 — Isolation + per-probe timeout
Each probe is wrapped so any exception/timeout becomes `reachable=False` + a `detail`, never propagating. A single configurable per-probe timeout (a new `settings` field, small default e.g. 5s) bounds each call; the endpoint's worst case is roughly the slowest single probe when probes run concurrently, or the sum when sequential. **Decision: run the probes concurrently** (thread pool) so the page's worst case is one timeout, not four. Rationale: the service is sync (SQLAlchemy sync stack); a `ThreadPoolExecutor` with per-future timeout is the least-surprising fit and keeps each probe's own blocking client intact. Alternative (sequential): simpler, but a page that can take 4× the timeout is a worse diagnostic. Alternative (async): the providers/broker are sync `requests`/`yfinance`, so going async would mean wrapping them anyway.

### D4 — Secret hygiene
Schemas carry only booleans + non-secret identifiers. No probe result or `detail` string interpolates a key/secret/token. Where an underlying error message might embed a URL with a token (not expected here, but defensively), the `detail` is a short, fixed classification (e.g. "unauthorized", "timeout", "unreachable") derived from the exception type/status rather than the raw message.

### D5 — Frontend: a polling read-only page mirroring `TechnicalIndicatorsPage`
`api/system.ts` with `systemKeys`, `getSystemStatus()`, and `useSystemStatus()` (a `useQuery` with a modest `refetchInterval`, e.g. 30s, plus the query's own `refetch` wired to a manual "Refresh" button). `pages/system/SystemStatusPage.tsx` renders a `SectionCard`/card per backend with a status pill (green reachable / red unreachable / slate unavailable-or-stub), the identifier, and latency; pending and error states as in the template. New `NAV_ITEMS` entry "System" + a new icon; new `<Route path="system">` in `App.tsx`; types mirrored in `types/api.ts`.

## Risks / Trade-offs

- **Outbound calls + possible API cost/rate on each page load** → probes are the cheapest calls available (`models.retrieve`, 1-result search, `/v2/clock`, single `fetch_info`); polling interval kept modest (30s) and only while the page is open; manual refresh for on-demand checks.
- **A hung backend delaying the page** → mandatory per-probe timeout + concurrent execution bound the worst case to ~one timeout.
- **Constructing `AlpacaBroker` triggering the global 503 handler** → the probe constructs and calls the broker inside its own try/except and never relies on `Depends(get_broker)`, so broker failures stay contained in the backend's status entry.
- **`models.retrieve` behavior across model ids / proxies** → if an org can't retrieve a model it can still use, the probe may report unreachable while the model works; acceptable for an informational page, and the `detail` will distinguish "unauthorized" (key problem) from "model not found" (model id problem). If this proves noisy, a `models.list()` fallback is a later tweak and does not change the spec.
- **yfinance has no stub** → the probe always makes a real network call for market data even in otherwise-offline/dev setups; acceptable because the page is an explicit on-demand diagnostic, and it is the one backend with no credential to gate on.

## Migration Plan

Additive only: new package, router, schemas, frontend page/route/nav, and one new `settings` timeout field (with a safe default). No DB migration, no changes to existing endpoints or hot paths. Rollback = remove the router registration + nav entry/route; nothing persisted to unwind.
