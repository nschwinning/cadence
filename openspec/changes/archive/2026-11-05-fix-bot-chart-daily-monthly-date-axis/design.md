## Context

`buildBotValueOption` in `frontend/src/pages/bots/BotValueChart.tsx` builds one ECharts
option for all four resolutions on a single `xAxis: { type: 'time' }`. `type:'time'` ticks
are placed by ECharts in the browser's local timezone (no `useUTC`), while the daily/monthly
label/tooltip formatters read the UTC calendar date. For a viewer east of UTC the two
disagree, duplicating date labels and bleeding a day's value onto the neighbouring label.
See proposal.md — Root cause. The daily/monthly backend data is already one row per period.

## Goals / Non-Goals

**Goals:**
- Daily/monthly: exactly one x-axis tick per period, each with its own end-of-day value,
  timezone-independent.
- Keep intraday (`5min`/`hourly`) exactly as-is (local-time `type:'time'` axis).
- Preserve daily/monthly carry-forward-to-today-ET.
- Keep the fix unit-testable without asserting on ECharts' internal tick generation.

**Non-Goals:**
- No backend/API/retention/downsampling change (data is already correct).
- No fixed x-axis windows/caps (user chose "just fix the bug").
- No change to the freshness badge, resolution switcher, or the 5m default.
- Not the hourly "only yesterday afternoon" gap — that is an intraday-capture/freshness
  matter, out of scope here.

## Decisions

**Decision: daily/monthly use a `type: 'category'` x-axis keyed by the series' own date
labels; intraday keeps `type: 'time'`.**
- A category axis renders exactly one tick per supplied category, so there is no sub-day
  tick generation and no local-vs-UTC placement ambiguity — the duplication and neighbour
  bleed cannot occur. Categories are the already-UTC-derived date strings the data carries,
  so labels are deterministic and match the data.
- `buildBotValueOption` branches on `isIntradayResolution(resolution)`:
  - intraday → unchanged: `type:'time'`, `[Date.parse(timestamp), value]` series, local-time
    `formatIntradayAxis`/`formatIntradayTooltip`.
  - daily/monthly → `type:'category'` with `data` = the ordered period labels (`dd.MM` for
    daily; `dd.MM`/`MM.yyyy`-style for monthly, matching today's format helpers), and the
    line series values aligned to those categories. Carry-forward-to-horizon still runs
    first to produce the ordered period list; the horizon/today-ET point remains the last
    category.
- Tooltip for the coarse branch shows the period's `dd.MM.yyyy` (daily) label and value,
  read from the hovered category rather than an epoch.

**Alternatives considered:**
- Keep `type:'time'` and set `useUTC`: `useUTC` is a global ECharts init option, not
  per-axis, so it would also force intraday into UTC — which we deliberately want in local
  time. Rejected.
- Keep `type:'time'` with `minInterval: 1 day` + aligned `interval`: still timezone-sensitive
  at DST edges and harder to unit-test than an explicit category list. Rejected.

## Risks / Trade-offs

- [Category axis spaces points evenly, not by true time gap] → acceptable and arguably
  preferable for a daily/monthly equity curve (one slot per period); the carry-forward
  already fills non-trading days so weekends read flat rather than as gaps.
- [Two code paths for the axis] → mitigated by the existing `isIntradayResolution` branch
  already present for plotting; the axis branch sits alongside it.
