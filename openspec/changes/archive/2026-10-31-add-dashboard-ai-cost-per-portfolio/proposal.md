## Why

The session-detail page already shows a per-session "AI cost" KPI tile (cumulative LLM
spend for that one session, read from the LiteLLM proxy's `SpendLogs`). But there is no
single place to compare AI cost **across** portfolios. An operator running several
paper-trading portfolios has no overview of where the LLM spend is going, so cost creep
on any one portfolio is invisible until they open each session individually.

This change adds a dashboard panel listing AI cost **per portfolio** with a grand total,
giving an at-a-glance spend overview.

## What Changes

- A new backend endpoint returns **all-time cumulative** AI cost **per portfolio** plus a
  grand total, for all **active** paper-trading sessions, independent of the dashboard's
  range selector. It reads the same LiteLLM `SpendLogs` source as the per-session tile, but
  aggregates in a **single batched query** (`GROUP BY` the `cadence_session_id` metadata
  key) rather than one query per session.
- A new dashboard UI panel renders one row per portfolio (label + cost, sorted by cost
  descending) and a total row. It reuses the existing cost-degradation convention: when
  the cost source is unconfigured or unavailable the panel shows an em dash and an
  explanatory hint instead of `$0.00` or an error.
- The existing `GET /dashboard/overview` endpoint, its range/selection behavior, and the
  per-session AI cost tile are left unchanged.

### Decision: a dedicated endpoint, not a field on the overview

The requested data is all-time and range-independent. The existing `/dashboard/overview`
is range-scoped (and would couple cost to the range). Adding an `ai_cost` field there would
be semantically wrong and would force per-session cost queries inside the range loop. So
this adds a separate endpoint. Rationale is captured in `design.md`.

### Scope: active sessions only

The breakdown covers **active** paper-trading sessions only (stopped and archived sessions
are excluded), matching the scope of the existing dashboard overview.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `dashboard`: adds a requirement for a per-portfolio, all-time AI cost breakdown endpoint
  over active sessions (new behavior alongside the existing overview/metrics endpoints).
- `app-shell`: adds a requirement for the dashboard AI-cost-per-portfolio panel (placement
  above the market-performers tiles, UI rendering, ordering, total, and cost-unavailable
  degradation).

## Impact

- **Backend**: `paper_trading/ai_cost.py` gains a batched multi-session cost helper
  (the existing single-session helper stays); `dashboard/service.py` gains a new service
  function + frozen dataclass(es); `api/routers/dashboard.py` gains a new endpoint;
  `api/schemas.py` gains the matching read schema(s). No migration, no DB column changes
  (`SpendLogs` lives read-only in the LiteLLM database).
- **Frontend**: `types/api.ts` gains the response types; `api/dashboard.ts` gains a hook;
  a new dashboard panel component is added and rendered in `DashboardPage.tsx`.
- **Deploy**: no new infra. The panel only shows real figures when `LITELLM_DATABASE_URL`
  is configured and the `litellm` database is reachable (same precondition as the existing
  per-session tile); otherwise it degrades to the em-dash/unavailable state.
