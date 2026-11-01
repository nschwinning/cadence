## Context

See proposal.md — Why. The daily snapshot job
(`backend/src/cadence/ai_portfolio/snapshots.py::snapshot_all_sessions`,
lines ~129-139) deliberately skips sessions holding no crypto on weekends, so an
equity-only session has no `SessionValueSnapshot` for Sat/Sun. The value-history
and comparison endpoints return the stored rows verbatim; the three charts plot
only the points that exist, so equity-only lines end on Friday.

Relevant existing frontend state:

- `pages/paper-trading/SessionComparisonChart.tsx` — `buildComparisonSeries`
  maps each session's own `points` onto an ECharts `type: 'time'` axis. No shared
  axis, no fill. **This is where the reported bug is most visible** (equity-only
  sessions compared against crypto sessions that do have weekend points).
- `pages/paper-trading/SessionValueChart.tsx` — single session value + benchmark
  overlay, same stored-points-only model.
- `pages/dashboard/aggregate.ts` — `combinedSeries` **already** carries each
  session forward over the union of the selected sessions' dates (LOCF), and
  `benchmarkDollarSeries` carries indices forward via `closeOnOrBefore`. The
  dashboard's only gap is that the union axis ends at the last snapshot date, so
  a trailing weekend is not shown.

Snapshot dates are ET calendar dates (`YYYY-MM-DD`). `lib/format.ts` already has
UTC-safe date handling (`formatAxisDate`) that the chart axes use.

## Goals / Non-Goals

**Goals:**

- Draw each session's line flat at its last recorded value across dates it has no
  snapshot for (weekends / non-trading days), consistently across the comparison,
  single-session, and dashboard combined-equity charts.
- Extend each chart's shared date axis to a trailing horizon of **today (ET)** so
  the current weekend reads flat rather than ending on Friday.
- A single, pure, unit-tested carry-forward/date-axis helper reused by all three
  charts, mirroring the `pages/dashboard/aggregate.ts` pure-helper pattern.

**Non-Goals:**

- Writing weekend snapshots or touching the snapshot job / its weekend skip.
- Any backend, endpoint, schema, migration, KPI, P&L-push, or learning-snapshot
  change.
- Backfilling values before a series' first snapshot (lines still start at their
  first real point).
- Changing chart toggles, legends, axes, colors, tooltips, or default indices
  beyond the added carried-forward points.

## Decisions

### D1: Fix in the frontend presentation layer, not the data layer

Carry-forward is applied when building the chart series; stored snapshots are
untouched. **Alternative considered:** persist weekend carry-forward rows in the
snapshot job, or synthesize them in the comparison endpoint. Rejected because
extra rows would distort `daily_avg_transaction_cost` (= `total_fees` ÷ number of
value snapshots) and the day-over-day P&L performer metric, and would entangle
the fix with the P&L push and learning-snapshot side effects. A pure read-model
fill in the backend was also rejected to keep the change frontend-only and avoid
duplicating the LOCF logic the dashboard already has client-side. Confirmed with
the user: presentation-only.

### D2: Last-observation-carried-forward over a shared date axis, extended to today (ET)

A shared helper builds a sorted, de-duplicated date axis from the union of the
input series' dates, then appends a trailing horizon equal to `max(latest axis
date, today-ET)` (and the in-between non-trading days needed to render a flat
segment — in practice ECharts draws a straight segment between two equal-valued
points, so only the endpoint date is required). For each series it emits, for
every axis date on or after that series' first point, the value of the most
recent point on or before that date. Dates before the first point get no value
(null / omitted) — no backfill.

- **Comparison chart:** axis = union of all displayed sessions' dates + today;
  LOCF each plotted session. Equity-only sessions then extend flat alongside
  crypto sessions. Return-% vs Value-$ is computed from the carried-forward value
  exactly as today (carry-forward happens on the value series before the metric
  transform, so a flat value ⇒ a flat return).
- **Single-session chart:** axis = the session's own dates + today; LOCF the
  value line and the benchmark overlay (benchmark shares the same snapshot dates,
  so it carries forward alongside for visual consistency).
- **Dashboard combined-equity:** reuse the existing `combinedSeries` /
  `benchmarkDollarSeries` LOCF, but feed them a date axis extended to today.
  `combinedSeries` currently derives its own union internally; it (or its caller)
  is adjusted to include the today horizon so the combined and benchmark lines
  extend flat over the trailing weekend. No other dashboard behavior changes.

**Today (ET):** derive the horizon date as the current calendar date in
`America/New_York`, formatted as `YYYY-MM-DD`, so it compares lexicographically
against snapshot date strings and stays consistent with how snapshots are keyed.
Reuse / extend `lib/format.ts` date helpers rather than introducing a new date
library.

### D3: Benchmark carried forward alongside its session line

On the single-session and dashboard charts the benchmark is derived from the same
snapshot/trading-day cadence, so it is carried forward on the same axis to keep
the portfolio and benchmark lines visually aligned (both flat over the weekend).
This is already true on the dashboard via `closeOnOrBefore`; the single-session
chart extends its benchmark the same way. **Alternative:** carry forward only the
portfolio line and let the benchmark end early — rejected as visually
inconsistent.

## Risks / Trade-offs

- [A flat line to "today" could look like fresh data on a weekday before the
  16:15 ET snapshot] → This matches the real meaning (value is unchanged since
  the last close) and the single-session chart already shows an "End of day"
  indicator explaining the latest point reflects the prior close. No new value is
  invented; the segment is explicitly flat.
- [Refactoring `combinedSeries` risks regressing the dashboard aggregate] → Keep
  its LOCF logic intact and change only the date axis it iterates; existing
  `aggregate.test.ts` cases plus new trailing-horizon cases guard it.
- [Time-zone edge near ET midnight could place the horizon a day off] → Acceptable
  for a chart; the horizon only ever extends the axis by at most a day and never
  alters a real snapshot's value.

## Migration Plan

Pure frontend change; no migration, no data backfill, no deploy ordering. Ships
with the frontend bundle. Rollback = revert the frontend commit.
