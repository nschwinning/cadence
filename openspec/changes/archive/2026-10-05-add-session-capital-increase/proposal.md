## Why

A paper-trading session's capital is fixed at build time and can never change. Operators want to add more capital to a running session (e.g. to top up a strategy that is doing well) without starting a new session and losing its track record. A naive capital bump, however, silently corrupts every return figure, because all analytics treat the starting capital as a single immovable cost basis: raising it dilutes historical return %, and retroactively shifts the benchmark overlay. To add capital *and* keep the numbers honest, the session needs a record of when capital was contributed and a return calculation that is not fooled by cash injections.

## What Changes

- **Add a capital-events ledger**: a new `session_capital_events` table records each capital contribution (session, positive amount, effective date). The session's original build-time capital is the first (implicit) contribution.
- **Increase a session's capital**: a new operation adds a positive amount to a session. It records a capital event and raises the session's total contributed capital (`allocated_capital`); because session cash is derived, the added cash becomes investable and is deployed by the next rebalance. Non-positive amounts are rejected. No withdrawals/decreases (out of scope).
- **Switch session return analytics to time-weighted return (TWR)**: `total_return_pct`, Sharpe, max drawdown, and excess return are computed from a contribution-adjusted daily return series so a deposit is never counted as a gain and historical return % stays stable across a capital increase.
- **Make the benchmark contribution-aware**: the benchmark buy-and-hold curve "buys" additional units worth each contribution at that contribution's effective date, so `benchmark_return_pct` and `excess_return` remain comparable to the session's TWR instead of jumping when capital is added.
- **Surface the control in the UI**: the session detail page gains an "Add capital" input + button next to the Capital fact tile, mirroring the existing benchmark/scope switchers.
- `allocated_capital` continues to mean *total contributed capital*, so the existing Capital tile, list page, and comparison chart keep reading correctly after an increase.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `ai-paper-trading`: new capital-events ledger and increase-capital operation; session value/cash reflect contributed capital; session performance KPIs and the value-history benchmark comparison are computed as time-weighted, contribution-aware figures.
- `app-shell`: the paper-trading session detail view gains a capital-increase control.

## Impact

- **Backend**: new `session_capital_events` ORM model + Alembic migration (nullable-safe; existing sessions get their build-time capital as the baseline contribution); new `increase_session_capital` service fn + `InvalidCapitalChangeError`; new `POST /api/v1/paper-trading/sessions/{id}/capital` endpoint + `SessionCapitalIncreaseRequest` schema; TWR + contribution-aware rework of `session_kpis`, `list_value_history`, the `benchmark` module, and the dashboard narrative benchmark helper. No secrets involved.
- **Frontend**: `changeSessionCapital` raw fn + `useIncreaseSessionCapital` hook (invalidates sessions list + KPIs + value history); a capital-increase control on `PaperTradingSessionPage`. No new TS fields are strictly required beyond the existing `allocated_capital`, though a contributed-capital/starting-capital distinction may be surfaced.
- **Migration**: adds one table; round-trip (upgrade/downgrade) and `alembic check` must stay clean on the single linear head.
- **Behavioral**: reported return % for existing sessions with no capital events is unchanged (a single-contribution TWR reduces to today's simple return); only sessions that receive a capital increase see the new split-period math.
