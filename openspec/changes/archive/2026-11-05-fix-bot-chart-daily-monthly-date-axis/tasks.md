## 1. Branch the x-axis for coarse resolutions

- [x] 1.1 In `frontend/src/pages/bots/BotValueChart.tsx`, update `buildBotValueOption` so
  `daily`/`monthly` render on a `type: 'category'` x-axis whose categories are the ordered
  period labels derived (UTC-based, as today) from the carried-forward series, with the line
  series values aligned to those categories, and the tooltip reading the hovered period's
  `dd.MM.yyyy` label + value. Leave the `5min`/`hourly` branch (`type:'time'`,
  `formatIntradayAxis`/`formatIntradayTooltip`, raw-point plotting, no carry-forward)
  unchanged. Verify intraday behaviour is untouched by reading the diff.
- [x] 1.2 Confirm daily/monthly carry-forward-to-today-ET still runs (the horizon/today
  point remains the last category) and the trend-coloured single value line is preserved.

## 2. Tests

- [x] 2.1 In `frontend/src/pages/bots/BotValueChart.test.tsx`, add a daily case: given two
  snapshots on consecutive dates (e.g. `2026-11-03`, `2026-11-04`), assert the built option's
  coarse x-axis exposes exactly one entry per date (e.g. `option.xAxis.data` equals the two
  `dd.MM` labels, no repeats) and each label maps to its own value (no neighbour-day bleed).
- [x] 2.2 Add a monthly case asserting one label per calendar month for snapshots spanning
  two months.
- [x] 2.3 Adapt the existing "labels daily ticks by calendar date with no clock-time or day
  shift" test to the category axis, and confirm the intraday local-time label tests
  ("labels intraday axis ticks and tooltips in the local timezone", "plots intraday points
  raw...") still pass unchanged.

## 3. Verify

- [x] 3.1 Run `cd frontend && npx vitest run && npx tsc --noEmit` and confirm all tests and
  the type check pass (frontend-only change; no backend gate needed).
