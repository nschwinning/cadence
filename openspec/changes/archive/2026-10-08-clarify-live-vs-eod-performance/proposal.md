## Why

On the paper-trading session detail page, the performance KPI tiles and the value
chart legitimately disagree intraday: the KPI tiles are **live** (the session KPI
summary marks open positions to market against current broker quotes and adds a
return leg up to "now"), while the value chart plots **only persisted end-of-day
value snapshots** (its last point is the prior close). The two reconverge once the
day's snapshot lands, but with nothing on screen to explain the difference a user
reasonably reads it as a bug. We want to make the distinction explicit rather than
change any computation.

## What Changes

- Add a clear **"Live"** indicator to the session performance KPI tiles section on the
  session detail page, signalling that those figures reflect current broker quotes.
- Add a clear **"End of day"** indicator to the session value history chart, signalling
  that the chart shows end-of-day snapshots and its latest point is the prior close.
- Each indicator carries a brief explanatory hint (e.g. tooltip/helper text) so a user
  can understand why the headline tiles and the chart's latest value can differ
  intraday.
- No change to KPI computation, value-history data, benchmark treatment, APIs, or
  storage. This is a presentation-only clarification.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `app-shell`: The "Session performance KPI tiles" requirement gains a live-data
  indicator, and the "Session value history chart" requirement gains an end-of-day
  indicator, so the detail page communicates that the tiles are live and the chart is
  end-of-day.

## Impact

- Frontend only: `frontend/src/pages/paper-trading/PaperTradingSessionPage.tsx` (KPI
  tiles section heading) and `frontend/src/pages/paper-trading/SessionValueChart.tsx`
  (chart heading), plus their co-located Vitest tests.
- No backend, service, schema, migration, or API change. Behavior and computed values
  are unchanged.
- Verify gate (frontend): `cd frontend && npm run typecheck && npx vitest run && npm run build`.
