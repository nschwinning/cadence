## Why

The strategy-bot detail page's "Bot value" chart currently opens at the `daily`
end-of-day resolution, so on entering the page a viewer sees the coarse snapshot
curve and must manually switch to `5m` to see how the bot has moved intraday.
Since the page already captures per-tick intraday points and the bots run on an
intraday cadence, the most useful first view is the live intraday series — so the
chart should open at `5min` by default.

## What Changes

- The bot detail "Bot value" chart SHALL open at the `5min` intraday resolution by
  default when the page is entered, instead of `daily`.
- On first load the resolution switcher reflects `5m` as the active selection and
  the freshness badge reads "Intraday"; the user can still switch to any other
  resolution (`1h`, `1D`, `1M`).
- No backend change, no endpoint/shape change, no change to the switcher options,
  ordering, carry-forward/intraday plotting, badge logic, or label timezones — only
  the initial selected resolution changes.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: the bot value chart requirement set gains a stated default/initial
  resolution — the chart opens at `5min` (intraday) when the page is entered, with the
  user still able to switch resolutions. No existing requirement currently pins the
  initial resolution.

## Impact

- Frontend only: `frontend/src/pages/bots/BotValueChart.tsx` — the `BotValueChart`
  component's initial `useState<BotValueResolution>` default changes from `'daily'` to
  `'5min'`.
- Tests: `frontend/src/pages/bots/BotValueChart.test.tsx` — the cases that assume the
  default load is `daily` (aria label, default fetch param, default freshness badge)
  are reworked to assume `5min`, while still covering a switch to a coarse resolution.
- No backend, API, migration, or dependency impact.
