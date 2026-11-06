## Why

The dashboard's "Total value" number visibly changes on its 30-second refetch even while the US equity market is closed, which looks like a bug but is expected behaviour: crypto is priced live 24/7 while equities are marked to their last official daily close when the market is closed. Nothing on the dashboard tells the viewer whether the market is open, so the moving number is confusing. Surfacing an honest market open/closed label makes the live value legible without changing any valuation.

## What Changes

- The dashboard overview payload gains a boolean `market_open` reporting whether the US equity market is currently open, derived from the broker clock (`Broker.is_market_open()`) that the overview service already has in hand.
- The clock call is wrapped so any broker/clock failure falls back safely and never fails the overview (mirrors the existing `_market_is_open` default-open convention in paper trading); the overview keeps returning `200`.
- The dashboard header renders a dot+label `role="status"` badge ("Market open" / "Market closed") next to the existing health indicator, auto-updating on the same 30s cadence as the rest of the overview.
- Valuation behaviour is unchanged: crypto stays live, equities stay frozen to last official close when the market is closed, strategy bots keep using their last stored tick/snapshot, and the 30s refetch cadence is untouched. The label only explains the behaviour; it does not alter it.

## Capabilities

### New Capabilities

<!-- none -->

### Modified Capabilities

- `dashboard`: the range-scoped overview additionally reports the current equity market open/closed state (derived from the broker clock with a safe fallback that never fails the overview), and the dashboard displays a corresponding market-state label.

## Impact

- Backend: `dashboard/service.py` (`DashboardOverview` dataclass gains `market_open`, `get_dashboard_overview` populates it from the injected broker with a safe fallback), `api/schemas.py` (`DashboardOverviewRead` gains the field), `api/routers/dashboard.py` (already injects `BrokerDep`; passes it through — no new endpoint).
- Frontend: `types/api.ts` (`DashboardOverview` gains `market_open`), `pages/dashboard/DashboardPage.tsx` (new market-state badge in the header, following the existing `HealthIndicator` dot+label `role="status"` pattern). Fetched via the existing `useDashboardOverview` hook (30s refetch).
- No database migration (computed field, not persisted). No new endpoint. No change to `compute_session_value`, EOD-vs-live gating, crypto-live pricing, strategy-bot valuation, total-value aggregation, or the refetch cadence.
