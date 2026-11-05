## Why

On the bot detail "Bot value" chart, a viewer east of UTC (the user is in CET) sees
calendar dates **repeated** on the `daily` (and `monthly`) x-axis, and a day's value can
appear under the **neighbouring** day's label — the user saw two different values both
labelled "03.11". The backend daily series is correct (exactly one end-of-day snapshot per
date); the fault is purely in how the chart renders the coarse resolutions, so the chart
misrepresents clean data.

## What Changes

- The `daily` and `monthly` chart resolutions SHALL render each calendar period **exactly
  once** on the x-axis with its own correct end-of-day value — no duplicated date labels and
  no value bleeding onto an adjacent period — independent of the viewer's timezone.
- The intraday resolutions (`5min`/`hourly`) are unchanged: they keep rendering local-time
  labels on the time axis, which is the desired behaviour for true captured instants.
- No new windowing/caps: the chart keeps showing all available history (daily fills toward
  30 days, monthly toward 48 months, hourly to the 30-day retention) as the bot ages.

## Root cause

In `frontend/src/pages/bots/BotValueChart.tsx`, all resolutions share one
`xAxis: { type: 'time' }`. ECharts places `type:'time'` ticks in the browser's **local**
timezone (no `useUTC` is set anywhere), i.e. on local (CET) midnight = 23:00 UTC the prior
day, while the daily/monthly label formatters (`formatAxisTimestamp`/`formatTooltipTimestamp`
in `lib/format.ts`) derive the date string from **UTC** (`toISOString().slice(0,10)`). The
local tick placement and the UTC label string disagree, so a viewer east of UTC gets
duplicate date labels and neighbour-day value bleed; with only 2–3 days of data the short
span makes ECharts tick at sub-day intervals, amplifying the duplication.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: the "Bot value chart local-timezone labels" requirement — its daily/monthly
  guarantee is tightened to be explicit and testable (each date/month appears exactly once with
  its own end-of-day value, never duplicated or shifted onto an adjacent period by the viewer's
  timezone). The intraday scenario is preserved verbatim.

## Impact

- Frontend only: `frontend/src/pages/bots/BotValueChart.tsx` — `buildBotValueOption` branches
  the x-axis so `daily`/`monthly` use a one-tick-per-period (category) axis keyed by the
  series' own date labels; `5min`/`hourly` keep the local-time `type:'time'` axis unchanged.
- Tests: `frontend/src/pages/bots/BotValueChart.test.tsx` — add/adapt daily and monthly cases
  asserting one axis label per period with its own value.
- No backend, API, migration, or dependency impact; the daily/monthly data is already correct.
