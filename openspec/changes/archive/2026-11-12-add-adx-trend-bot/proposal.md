## Why

Tier 1 of the strategy-bot roadmap is complete; the agreed next bot is **ADX Trend Strength**
(Tier 2 #6, course Algo 12). The same directional-movement maths also unlocks the course
**Algo 15 (VWAP + ADX Monitoring)** recipe, which was deliberately skipped for the
Rolling-Average Reversion bot because its "ADX danger exit" had no equivalent. Shipping both
gives manual users and the orchestrator a trend-strength bot and the last missing reversion
preset.

## What Changes

- New strategy **ADX Trend Strength** (`adx_trend`), pure and long-only (Algo 12): true range and
  ±DM per bar, +DI/−DI over rolling `period` sums, DX, ADX = mean of the latest `period` DX
  values (the course uses plain sums, not Wilder smoothing). Enter long when ADX > `threshold`
  and +DI > −DI; exit when ADX falls below `threshold`. Short leg dropped.
- **Rolling-Average Reversion gains an optional ADX danger exit** (Algo 15): while holding a
  losing position, exit when DX over the last `adx_lookback` bars exceeds `adx_threshold` and
  −DI > +DI. Off by default — existing presets and sessions behave exactly as before.
- Presets: **ADX Trend Strength (Algo 12)** — default: period 10, threshold 20, TP 0.5%, SL 1%,
  drawdown 5%. **VWAP + ADX Reversion (Algo 15)** — typical-price average, window 20, bare cross,
  bracket exit, ADX danger exit (lookback 20, threshold 20), TP 0.5%, SL off, drawdown 5%.
- Build form inputs for both; strategy guide illustration for ADX; roadmap updated (ADX shipped,
  Algo 15 preset added).
- No migration, no settings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: adds the ADX Trend Strength strategy; adds the ADX danger exit to the
  Rolling-Average Reversion strategy; adds two presets to the catalog.

## Impact

- Backend: new `strategy_bots/adx_trend.py` (strategy + shared directional-movement helpers),
  `rolling_average_reversion.py` (filter params and exit), `constants.py`, `registry.py`,
  `presets.py`.
- Frontend: `BuildBotCard.tsx` (ADX inputs; reversion ADX-exit inputs), new `adxChart.ts`
  registered in `strategyCharts.ts`.
- Docs: `docs/trading-bots-roadmap.md`.
