## Why

Next on the strategy-bot roadmap (`docs/trading-bots-roadmap.md`, Tier 2 #9) is **MA Ribbon**,
course Algo 18: three simple moving averages that must stack in order before the bot buys — a
stricter trend confirmation than the two-average crossover.

## What Changes

- New strategy **MA Ribbon** (`ma_ribbon`), pure and long-only: SMAs of the latest fast / mid / slow
  closes; enter long when fast > mid > slow. While holding, exits are left to the engine's
  take-profit / stop-loss bracket and drawdown kill-switch (the course exits only that way). Short
  leg dropped.
- Preset **MA Ribbon (Algo 18)** — default: 5 / 10 / 20, TP 0.5%, SL 1%, drawdown 5%.
- Build form inputs, a strategy-guide illustration, roadmap update.
- No migration, no settings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: adds the MA Ribbon strategy and its preset.

## Impact

- Backend: new `strategy_bots/ma_ribbon.py`; `constants.py`, `registry.py`, `presets.py`.
- Frontend: `BuildBotCard.tsx` (fast / mid / slow inputs), new `maRibbonChart.ts` registered in
  `strategyCharts.ts`.
- Docs: `docs/trading-bots-roadmap.md`.
