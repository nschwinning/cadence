## Why

On the strategy-bot detail page the "Bot value" chart renders **intraday** timestamps in **UTC** while the trade ledger on the same page renders dates/times in the browser's **local** timezone (CET for the user). The same page therefore disagrees with itself: a tick the chart labels `14:05` is shown by the trade ledger (and the live-value hint) as `15:05` CET.

The cause is purely in the frontend label formatting. In `frontend/src/pages/bots/BotValueChart.tsx` the intraday axis/tooltip formatters build their `HH:mm` strings by slicing `new Date(ms).toISOString()` — i.e. UTC — via `formatIntradayAxis` and `formatIntradayTooltip`. The ECharts x-axis is `type: 'time'` with a **custom** `axisLabel.formatter`/tooltip `formatter`, so ECharts' own timezone handling is bypassed and the UTC drift comes solely from `.toISOString()`. The underlying series epoch values (`Date.parse(p.timestamp)`) are correct; only the labels are wrong. By contrast the trade ledger uses `ts(value) => new Date(value).toLocaleString()` (`BotSessionPage.tsx`), which renders in the browser's local zone — hence CET. Backend intraday value-history points carry the true capture instant (`timestamp = captured_at`, a tz-aware UTC ISO datetime), so rendering them in the viewer's local zone is correct and is what the rest of the page already does.

## What Changes

- **Intraday chart labels become local-time.** `formatIntradayAxis` and `formatIntradayTooltip` in `BotValueChart.tsx` render their `dd.MM HH:mm` (axis) and `dd.MM.yyyy HH:mm` (tooltip) strings from the viewer's local timezone instead of UTC-sliced ISO parts. The output format (field order, zero-padding, separators) is unchanged — only the timezone basis flips, so intraday clock times match the page's trade timestamps.
- **Daily/monthly are deliberately left untouched.** Daily snapshot points are backend-stamped at `23:59:59 UTC` so a day's end-of-day point sorts after that day's intraday points on the shared timeline; the daily/monthly formatters (`formatAxisTimestamp`/`formatTooltipTimestamp` in `lib/format.ts`) read the UTC calendar **date** on purpose, to avoid shifting the label one day forward for viewers east of UTC. These resolutions show only a date (no clock time), so there is no visible timezone bug there.

## Capabilities

### Modified Capabilities
- `strategy-bots`: adds a requirement that the bot value chart's intraday (`5min`/`hourly`) axis labels and tooltips render in the viewer's local timezone (consistent with the page's trade timestamps), while the `daily`/`monthly` resolutions continue to label points by their snapshot calendar date.

## Impact

- Frontend only: `frontend/src/pages/bots/BotValueChart.tsx` (`formatIntradayAxis`, `formatIntradayTooltip`) and its vitest. No change to `lib/format.ts` daily/monthly helpers, the trade-ledger/KPI formatters (already local), or any shared util.
- No backend change: value-history timestamps, the `23:59:59 UTC` daily stamp, the endpoint shape, and the intraday capture job are unchanged.
- No ECharts `useUTC` change (it is unset and irrelevant — the custom formatters override ECharts' own time formatting).
