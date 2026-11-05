## 1. Change the default resolution

- [x] 1.1 In `frontend/src/pages/bots/BotValueChart.tsx`, change the `BotValueChart`
  component's initial resolution state from `useState<BotValueResolution>('daily')` to
  `useState<BotValueResolution>('5min')`. Verify by reading the file that no other logic
  (switcher options/order, `useBotValueHistory` call, carry-forward/intraday plotting,
  badge logic, label formatters) changed.

## 2. Update tests

- [x] 2.1 In `frontend/src/pages/bots/BotValueChart.test.tsx`, rework the cases that
  assume the default load is `daily` so the default is now `5min`:
  (a) "renders the chart for at least two points" — mock returns `resolution: '5min'`
  and assert the aria label matches `/bot value over 2 5min points/i`;
  (b) "refetches with the new resolution when the switcher changes" — assert the DEFAULT
  fetch is made with `params: { resolution: '5min' }` and the chart first renders
  `/5min points/i`, then switching to `1D` refetches with `{ resolution: 'daily' }`;
  (c) "marks the badge end-of-day for coarse resolutions and intraday for 5m" — assert
  the DEFAULT badge is `freshness-intraday` / "Intraday", then switching to `1D` flips it
  to `freshness-eod` / "End of day".
- [x] 2.2 Add (or fold into 2.1) an assertion that on first render the `5m` switcher
  button has `aria-pressed="true"` and the default value-history fetch param is `5min`,
  pinning the new default. Verify the case fails before the 1.1 edit and passes after.

## 3. Verify

- [x] 3.1 Run `cd frontend && npx vitest run && npx tsc --noEmit` and confirm all tests
  and the type check pass (frontend-only change; no backend gate needed).
