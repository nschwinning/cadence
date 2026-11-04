## 1. Extend the shared freshness badge

- [x] 1.1 In `frontend/src/pages/paper-trading/PaperTradingSessionPage.tsx`, widen
  `FreshnessBadge`'s `kind` prop to `'live' | 'eod' | 'intraday'`. Add the
  `intraday` case: label "Intraday", neutral grey styling consistent with `eod`
  (slate background/dot), `data-testid="freshness-intraday"`, and a tooltip
  explaining it shows per-tick intraday points whose latest point is the last
  captured tick and can lag the live figures. Leave the `live` and `eod`
  branches unchanged.

## 2. Make the bot value chart badge resolution-aware

- [x] 2.1 In `frontend/src/pages/bots/BotValueChart.tsx`, replace the hardcoded
  `badge={<FreshnessBadge kind="eod" />}` with a resolution-driven choice:
  `isIntradayResolution(resolution)` → `kind="intraday"`, else `kind="eod"`.

## 3. Tests and gates

- [x] 3.1 In `frontend/src/pages/bots/BotValueChart.test.tsx`, assert the chart
  shows the "End of day" badge at the default `1D` resolution and switches to an
  "Intraday" badge (`freshness-intraday`) after selecting `5m`, then back to
  "End of day" when a coarse resolution is reselected.
- [x] 3.2 Add/adjust a `FreshnessBadge` test so the `intraday` kind renders the
  "Intraday" label and `freshness-intraday` testid. Keep the existing live/eod
  assertions green.
- [x] 3.3 Run `cd frontend && npx vitest run && npx tsc --noEmit` and confirm all
  green. (No backend change; backend gate not required.)
