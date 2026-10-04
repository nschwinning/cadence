## Why

Cadence depends on four external backends — the Alpaca broker, the web-search provider (SerpAPI or Serper), yfinance market data, and the OpenAI agent model — but there is no single place to see whether they are actually configured and reachable. Today the only runtime surface is `/health`, which checks the database only. When a build, rebalance, or recommendation misbehaves, the operator has no quick way to tell "is Alpaca down / is my key missing / is the model name wrong" without reading logs. A read-only admin page that live-probes each backend and reports reachable/unreachable + latency makes that diagnosis a glance instead of an investigation.

## What Changes

- Add a backend **system status** capability that live-probes each connected external backend on demand and returns a per-backend status (configured, reachable, latency, and a non-secret identifier such as mode/provider/model).
- New read-only endpoint `GET /api/v1/system/status` returning the per-backend results. Each probe is isolated and time-bounded: one unreachable backend never fails the others or the overall response (endpoint always returns 200 with per-backend outcomes).
- Probes: **Alpaca** via its clock endpoint (reports paper/live/stub mode); **web search** via a minimal 1-result query against the active provider; **yfinance** via a single-ticker info fetch; **OpenAI** via a cheap model-retrieve that validates the key and the configured model id.
- Add an **admin "System Status" page** to the frontend shell: a new "System" navigation entry and a page that renders a card per backend (status pill + latency), with loading and error states, polling for freshness plus a manual refresh.
- **Secrets are never exposed**: the status surface reports only booleans (configured / key-present) and non-secret identifiers — never a key value.
- No persisted state and no database migration; this is purely an on-demand diagnostic view.

## Capabilities

### New Capabilities
- `system-status`: live, read-only reachability + latency probing of the app's external backends (Alpaca, web search, yfinance, OpenAI), exposed as `GET /api/v1/system/status`, with per-backend failure isolation, per-probe timeouts, stub-mode awareness, and no secret exposure.

### Modified Capabilities
- `app-shell`: the persistent shell's navigation requirement (which enumerates the app's nav entries) gains a "System" entry, and a new requirement covers the System Status page — its live-probe presentation and its loading/error/refresh behavior.

## Impact

- **Backend (new):** package `backend/src/cadence/system/` (probe service); router `backend/src/cadence/api/routers/system.py` registered in `api/routers/__init__.py` and mounted at `/api/v1` in `api/app.py`; new response schemas in the shared `api/schemas.py`. Reads existing `broker`, `assets/market_data`, `agents/tools` (web search), and `config.settings`. Uses the `openai` client (already a transitive dependency of `openai-agents`) for the OpenAI probe.
- **Frontend (new):** `src/api/system.ts` client + hook; `src/pages/system/SystemStatusPage.tsx`; new route in `src/App.tsx`; new nav item + icon in `src/components/layout/Sidebar.tsx`; types in `src/types/api.ts`.
- **No migration, no new persisted data.** No change to existing endpoints; `/health` is unaffected.
- **External calls:** the probe makes outbound requests to each backend only when the status endpoint is called (and for Alpaca only when not in stub mode); each is bounded by a short per-probe timeout.
