## Context

The bot detail "Bot value" chart (`frontend/src/pages/bots/BotValueChart.tsx`)
renders a `Panel` whose `badge` prop is hardcoded to
`<FreshnessBadge kind="eod" />`, so it always reads "End of day". The chart's
resolution switcher lets the user pick `5min`/`hourly` (intraday — raw per-tick
`bot_value_points`) or `daily`/`monthly` (the end-of-day snapshot curve). The
"End of day" label is only correct for the coarse resolutions.

`FreshnessBadge` is a shared component exported from
`PaperTradingSessionPage.tsx` and currently supports two kinds: `live` (green,
"Live") and `eod` (grey, "End of day"). The paper-trading page renders only
those two and must keep doing so.

## Goals / Non-Goals

Goals:
- The bot value chart's badge reflects the selected resolution: "Intraday" for
  `5min`/`hourly`, "End of day" for `daily`/`monthly`.

Non-Goals:
- No change to chart data, series, carry-forward, the resolution switcher, the
  value-history endpoint, intraday capture/retention, or the KPI tiles.
- No change to the paper-trading page's live/eod badges.
- No backend, schema, or migration change.

## Decisions

- **Extend `FreshnessBadge` with a third `intraday` kind** rather than invent a
  separate component, keeping one shared freshness primitive. The `intraday`
  kind uses neutral grey styling consistent with `eod` (it is explicitly *not*
  the green "Live" treatment, since intraday points are captured per tick, not
  marked-to-market at render time), label "Intraday",
  `data-testid="freshness-intraday"`, and a tooltip explaining the latest point
  is the last captured tick and can lag live. The `live`/`eod` branches are left
  byte-identical.
- **Choose the badge from the current resolution in `BotValueChart`** using the
  existing `isIntradayResolution(resolution)` helper: intraday →
  `kind="intraday"`, else `kind="eod"`. The badge is rendered from the
  component's `resolution` state, so it already recomputes when the switcher
  changes.

## Risks / Trade-offs

- Low risk; frontend presentation only. The existing `freshness-eod` testid and
  the paper-trading badges are unchanged, so current tests keep passing.
