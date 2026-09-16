## Context

See proposal.md - Why. The data for these KPIs already exists but is not exposed as a headline summary:

- `paper_trading/service.py::compute_session_value(session, *, session_id, broker) -> SessionValuation` already marks the open ledger to market via `broker.get_quotes` and returns `total_value`, `cash_value`, `positions_value`, and a per-position list. Each position dict carries `unrealized_pnl`, but the valuation's **top-level** does not expose the summed unrealised figure.
- `PaperTradingSession.total_pnl` is the cumulative realised P&L.
- `list_value_snapshots(session, *, session_id)` returns the ordered daily `SessionValueSnapshot` rows, each with `daily_pnl_pct` — the day's fractional NAV return. This is the ready-made input for a Sharpe calculation; no external price history is needed.
- The session router already has a broker DI (`BrokerDep`) used by the reconcile/valuation endpoints.

Frontend: `components/dashboard/StatTile.tsx` is the existing KPI card (`label`, `value: ReactNode`, optional `hint`). `PaperTradingSessionPage.tsx` renders the header and resource panels; currency is formatted with a per-file `eur` helper and P&L colour with a local `pnlClass()`. `api/paperTrading.ts` holds the query-key factory + hooks; `types/api.ts` hand-mirrors the schemas.

## Goals / Non-Goals

**Goals:**
- One read endpoint that returns all five KPIs, marking open positions to market on load.
- A pure, unit-testable Sharpe function fed by a plain list of daily returns.
- Reuse the existing valuation path and snapshot series; no new persistence.
- Reuse `StatTile` and consolidate currency/percent formatting into shared helpers.

**Non-Goals:**
- No holdings-based / yfinance-simulated Sharpe (the estimate uses the session's *actual* NAV series only).
- No caching of live valuation, no new polling loop (the KPI query loads with the page; it does not need `refetchInterval`).
- No database migration, no changes to order execution or the rebalancing cron.
- No configurable UI for the risk-free rate or annualisation factor (constants/settings only).

## Decisions

**Sharpe from the actual daily NAV series, gated on history.** The session's `daily_pnl_pct` snapshot series is the true daily-return series of the portfolio. Sharpe = `mean(returns) / stdev(returns) * sqrt(SHARPE_TRADING_DAYS_PER_YEAR)`, with returns taken in excess of a risk-free rate defaulting to 0. It returns `None` when there are fewer than `SHARPE_MIN_RETURNS` returns or when `stdev == 0`.
- *Why gate on the actual series rather than simulate from historical prices?* The user asked for Sharpe "based on the portfolio" and to show "Not yet available" until there is enough history. The actual-NAV approach is honest (it measures the session's real performance) and needs no new data source. A holdings-basket simulation from yfinance would be dense/immediate but would characterise the current basket, not the session's real track record — rejected.
- *Constants:* `SHARPE_TRADING_DAYS_PER_YEAR = 252`, `SHARPE_MIN_RETURNS = 20` (≈ one trading month). Risk-free rate defaults to 0, sourced from settings so it is tunable without a code change. Using sample standard deviation (n-1) is the conventional choice for a return sample.
- *Pure helper:* implement `sharpe_ratio(returns: Sequence[float], *, risk_free: float = 0.0) -> float | None` with no DB or I/O, so the maths is tested in isolation from the endpoint.

**Surface `unrealized_pnl` on the valuation rather than re-summing in the router.** Add a top-level `unrealized_pnl` field to the `SessionValuation` dataclass, populated inside `compute_session_value` from the same per-position marks it already computes (`unrealized_total`). Keeps the router thin and gives tests a single place to assert the summed figure. Alternative — summing the per-position dicts in the endpoint — was rejected as duplicating logic the service already has in hand.

**A dedicated `session_kpis` service function.** It loads the session (raising `SessionNotFoundError` when absent), calls `compute_session_value` for the live figures, reads `total_pnl` for realised P&L, derives both `total_return = current_value - allocated_capital` (absolute money) and `total_return_pct = total_return / allocated_capital` (fraction), and calls the Sharpe helper on the snapshot returns. The router maps `SessionNotFoundError -> 404` (same mapping the other session endpoints use) and `model_validate`s a new `PaperTradingSessionKpisRead`.
- *Total return, two forms:* the absolute money figure equals realised + unrealised P&L (= `current_value - allocated_capital`); both it and the fraction are returned so the UI can show `+€X (+Y%)` without recomputing. `allocated_capital` is always positive for a real session, so no divide-by-zero guard is needed beyond what session creation already enforces; the calculation stays in the service.

**Endpoint shape.** `GET /api/v1/paper-trading/sessions/{id}/kpis` (read, so GET; injects `BrokerDep`). Returns `PaperTradingSessionKpisRead { current_value, realised_pnl, unrealised_pnl, total_return, total_return_pct, sharpe_ratio: float | None }`. British spelling in the schema field names mirrors the proposal's KPI wording; the frontend type mirrors it exactly.

**Frontend: shared formatters + a non-polling hook.** Add `formatCurrency` and `formatPercent` to `lib/format.ts` (today each page redefines a currency formatter) and adopt them in the new KPI row; leave the pre-existing duplicates for a later cleanup to keep this change scoped. Add `useSessionKpis(sessionId)` with a `paperTradingKeys.kpis(sessionId)` key (enabled only when `sessionId` is non-empty, consistent with the other session hooks). Render the five `StatTile`s in a grid above the value chart; colour realised/unrealised/total-return via the existing `pnlClass()`; the total-return tile uses `formatCurrency(total_return)` as its value and `formatPercent(total_return_pct)` as its hint; show `sharpe_ratio` or, when null, "Not yet available" with a hint.

## Risks / Trade-offs

- **Sharpe reads sparse/young data** → gated by `SHARPE_MIN_RETURNS`, so a young session shows "Not yet available" rather than a noisy number; the threshold is a single constant, easy to tune.
- **KPI endpoint hits the broker on every page load** (live quotes) → acceptable: it mirrors what the snapshot cron already does, uses the existing `compute_session_value` path, and there is no new polling loop. If it ever becomes hot, a short-TTL cache can be added later without changing the contract.
- **Snapshot cadence assumption** — Sharpe treats each `daily_pnl_pct` as one daily return; if snapshots are ever recorded more/less than daily the annualisation factor would drift. Today snapshots are daily (cron-driven), matching the √252 assumption; noted as a constraint rather than a live risk.
- **British/American spelling split** (`unrealised` in KPI wording vs `unrealized_pnl` inside the existing valuation) → the schema field is fixed as `unrealised_pnl` and the frontend type mirrors the schema exactly, so the wire contract is unambiguous even though the internal dataclass keeps `unrealized_pnl`.
