## Why

The technical-indicator trend strategy (indicator set, the deterministic uptrend gate, and the reversal flags) is configured entirely in backend constants and is invisible from the UI — a user who opts a session into the trend strategy has no way to see what indicators are computed, what gate rules decide a candidate passes, or what thresholds are used. A read-only "Technical Indicators" page makes the configured setup transparent so users understand what the strategy actually does.

## What Changes

- Add a new **read-only** `GET /api/v1/technical-indicators/config` endpoint that returns the technical-indicator configuration derived from the backend constants: the fixed indicator set, the period/lookback parameters, the deterministic uptrend trend-gate rules + thresholds, and the reversal-flag definitions + thresholds. Unlike the existing `POST /technical-indicators/runs`, this endpoint is a plain unauthenticated read (NOT cron-guarded).
- Add a new top-level **"Technical Indicators"** navigation tab and an info-only page that fetches the config and renders the indicator list, the periods, the gate rules, and the reversal flags in readable grouped sections, with loading and error states.
- No per-asset data and no editing in this change — the page is informational for now; the gate/threshold values stay truthful because they come from the backend.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `technical-indicators`: add a read-only requirement that the system exposes the configured indicator set, periods, trend-gate rules + thresholds, and reversal-flag definitions + thresholds over an unauthenticated read endpoint.
- `app-shell`: add a requirement for a "Technical Indicators" navigation entry and an info-only page that displays the configured technical-indicator setup read from the backend, with loading/error states.

## Impact

- **Backend:** new `GET /api/v1/technical-indicators/config` route in `api/routers/technical_indicators.py`; new response schema(s) in `api/schemas.py`; a service/read helper assembling the config from `technical_indicators/constants.py`. No new ORM, no migration.
- **Frontend:** new nav item + icon (`components/layout/Sidebar.tsx`, `components/icons/`), new route (`App.tsx`), new page under `pages/technical-indicators/`, a new api module + TanStack Query hook (pattern from `api/dashboard.ts`), and a new type in `types/api.ts`.
- **No** database migration, no changes to the nightly precompute job or the existing cron-guarded runs endpoint, no change to how the trend strategy is applied during rebalances.
