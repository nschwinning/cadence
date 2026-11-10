## Why

Rolling-Average Reversion is the next strategy on the bot roadmap (Tier 1 #3) and its
biggest consolidation: several course algorithms are the same "buy when price sits below
its rolling average, sell as it reverts" signal with different averages and distance
measures. Shipping it as one configurable strategy, plus one preset per course algorithm,
gives manual users full flexibility and gives the future AI orchestrator four more vetted,
course-faithful configurations to choose from.

## What Changes

- Add a long-only **Rolling-Average Reversion** strategy with three configurable axes:
  - **average type**: simple mean of closes, mean of typical price ((high + low + close) / 3),
    or true volume-weighted average price over the window;
  - **distance**: a percentage band below the average (a zero band is a bare cross below
    the average) or a z-score in standard deviations;
  - **exit mode**: exit once price reverts toward the average, or hold and leave the exit to
    the engine's take-profit / stop-loss bracket.
- Register it in the strategy catalog with a display name and explanation.
- Add four course presets (one per algorithm), with **SMA Band Reversion (Algo 5)** as the
  strategy's default:
  - Algo 5: SMA, 20 bars, enter 1% below, exit within 0.5%; stop-loss 2%.
  - Algo 4: SMA, 20 bars, z-score enter below −1.0σ, exit above −0.2σ; stop-loss 2%.
  - Algo 14: SMA, 60 bars, bare cross, bracket exit; take-profit 0.5%, stop-loss 1%.
  - Algo 39: true VWAP, 60 bars, bare cross, bracket exit; take-profit 0.5%, stop-loss 1%.
  All use a 5% drawdown limit.
- Build form: add the strategy's parameter fields, and a general **preset selector** listing
  the selected strategy's presets (needed now that one strategy has four). The Donchian
  version selector keeps working and stays in sync with the selected preset.
- Strategy guide: an illustrative chart for the new strategy.
- No migration: strategy keys and presets are additive.

Deliberately out of scope:
- **Algo 15**: its stop is an ADX trend-strength exit. It gets a preset once an ADX exit
  filter exists. Typical price is still available for manual bots.
- **Algo 35**: it is trend-following (buys above the average, gated by volume), not
  reversion, so it will be a separate bot.

## Capabilities

### New Capabilities

<!-- None: the strategy and presets extend the existing strategy-bot capability. -->

### Modified Capabilities

- `strategy-bots`: adds the "Rolling-Average Reversion strategy" requirement; modifies
  "Bot preset catalog" (four new presets and the strategy's default) and "Preset-driven
  build form" (a preset selector for the selected strategy's presets).

## Impact

- **Backend**: new `strategy_bots/rolling_average_reversion.py`; `constants.py`
  (`StrategyKey`, display name, explanation); `registry.py`; `presets.py` (four presets).
  No schema, API-shape or migration change; the existing catalog and preset endpoints
  carry the new entries.
- **Frontend**: `BuildBotCard.tsx` (parameter fields, preset selector, payload,
  validation); new `rollingReversionChart.ts` registered in `strategyCharts.ts`.
- **Unchanged**: engine, sizing, valuation, KPIs, kill-switch, and every existing
  strategy's signal logic and presets.
