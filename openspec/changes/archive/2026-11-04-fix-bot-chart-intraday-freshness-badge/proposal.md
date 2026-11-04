## Why

On the bot detail page, the "Bot value" chart's freshness badge always reads
"End of day" regardless of the selected resolution. The badge is hardcoded, but
the 5m/1h intraday resolutions plot per-tick intraday points — not end-of-day
snapshots — so the label contradicts what the chart actually shows and misleads
the user about how fresh the data is.

## What Changes

- Make the bot value chart's freshness badge **resolution-aware**: show a new
  neutral "Intraday" badge when an intraday resolution (`5min`/`hourly`) is
  selected, and keep the existing "End of day" badge for the coarse resolutions
  (`daily`/`monthly`) that genuinely read the end-of-day snapshot curve.
- Extend the shared `FreshnessBadge` component with a third `intraday` kind
  (label "Intraday", neutral styling, explanatory tooltip). The existing `live`
  and `eod` kinds are unchanged.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: the bot detail value chart SHALL indicate data freshness in a
  way that reflects the selected resolution — intraday resolutions marked as
  intraday, coarse resolutions as end-of-day.

## Impact

- Frontend only. `frontend/src/pages/paper-trading/PaperTradingSessionPage.tsx`
  (`FreshnessBadge` gains an `intraday` kind) and
  `frontend/src/pages/bots/BotValueChart.tsx` (badge chosen from the current
  resolution).
- No backend, API, schema, or migration changes. The chart data, resolution
  switcher, value-history endpoint, and the paper-trading page's live/eod badges
  are untouched.
