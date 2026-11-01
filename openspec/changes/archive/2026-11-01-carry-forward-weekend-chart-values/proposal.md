## Why

An equity-only paper-trading portfolio (no crypto) gets no value snapshot on
weekends — the daily snapshot job deliberately skips it while the US equity
market is closed. As a result its line in the multi-session comparison chart
simply **ends at Friday**, so it disappears from the comparison on Saturday and
Sunday while crypto sessions (which do get weekend snapshots) keep going. The
user cannot see an equity-only portfolio's performance on weekends, even though
its value is unchanged from the preceding trading day. The expected behaviour is
a **flat carry-forward line** across weekend (and any other non-trading-day)
gaps, equal to the last recorded value.

## What Changes

- Carry each session's last recorded value **forward** across dates it has no
  snapshot for, when rendering the paper-trading charts — a flat line equal to
  the preceding trading day's value — instead of ending the line at the last
  stored point. This is a **presentation-only** change: stored value snapshots,
  the daily snapshot job and its weekend skip, daily P&L pushes, the learning
  snapshot job, and all KPIs are left exactly as they are.
- Extend each chart's shared date axis to a trailing horizon of **today (ET)** so
  an equity-only line also extends flat over the current weekend, not just up to
  the latest date some other session happens to have.
- Apply the behaviour across the three paper-trading charts:
  - **Session comparison chart** — carry each session forward over the union of
    all displayed sessions' dates (plus the today horizon), so equity-only
    sessions stay plotted alongside crypto sessions on weekends.
  - **Single-session value chart** — carry the value line (and its benchmark
    overlay) forward to the today horizon so the latest weekend reads flat.
  - **Dashboard combined equity curve** — its aggregation already carries values
    forward over the union of session dates; extend that shared date axis to the
    today horizon so the already-carried-forward combined line and benchmark
    lines extend flat over trailing non-trading days too.
- Introduce a shared, pure, unit-tested frontend carry-forward helper
  (last-observation-carried-forward over a shared date axis), mirroring the
  existing pure-aggregation helpers in `pages/dashboard/aggregate.ts`.

No backend, API, schema, migration, or data changes. No change to when or whether
snapshots are recorded.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `app-shell`: three dashboard/paper-trading chart requirements change their
  rendering behaviour to carry each session's value forward across dates with no
  snapshot (flat lines over weekends/non-trading days) and to extend the shared
  date axis to the current day:
  - `Session value history chart`
  - `Paper-trading session comparison chart`
  - `Dashboard combined equity curve`

## Impact

- **Frontend only.** New shared carry-forward/date-axis helper (e.g. under
  `frontend/src/lib/` or a charts util) plus wiring in
  `pages/paper-trading/SessionComparisonChart.tsx`,
  `pages/paper-trading/SessionValueChart.tsx`, and
  `components/dashboard/CombinedEquityChart.tsx` (the last via the shared date
  axis fed to `pages/dashboard/aggregate.ts`'s `combinedSeries` /
  `benchmarkDollarSeries`).
- **Unchanged:** the snapshot job and its weekend skip
  (`ai_portfolio/snapshots.py`), the value-history / comparison / overview
  endpoints' stored-row semantics, daily P&L pushes, the learning snapshot job,
  and every KPI (notably `daily_avg_transaction_cost`, which divides fees by the
  snapshot count and would be distorted by synthetic weekend rows).
- Verified during planning: `combinedSeries` and `benchmarkDollarSeries` in
  `pages/dashboard/aggregate.ts` already carry forward over the union of session
  dates, so the dashboard change is limited to extending the shared axis horizon.
