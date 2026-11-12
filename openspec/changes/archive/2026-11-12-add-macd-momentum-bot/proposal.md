## Why

Next on the strategy-bot roadmap (`docs/trading-bots-roadmap.md`, Tier 2 #5) is **MACD Momentum**,
course Algo 10: the classic EMA-difference momentum signal. It adds a momentum-confirmation bot
alongside the breakout, band, ADX and mean-reversion bots, for manual use and for the orchestrator's
preset catalog.

## What Changes

- New strategy **MACD Momentum** (`macd_momentum`), pure and long-only: fast/slow EMAs of closes
  (seeded from simple means, as in the course), MACD = fast − slow, signal = EMA of MACD. Enter long
  when MACD crosses above its signal line while MACD is above zero; while holding, exits are left to
  the engine's take-profit / stop-loss bracket and drawdown kill-switch (the course exits only that
  way). Short leg dropped.
- Preset **MACD Momentum (Algo 10)** — default: 12 / 26 / 9, TP 0.5%, SL 0.5%, drawdown 5%.
- Build form inputs, a strategy-guide illustration, roadmap update.
- No migration, no settings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: adds the MACD Momentum strategy and its preset.

## Impact

- Backend: new `strategy_bots/macd_momentum.py`; `constants.py`, `registry.py`, `presets.py`.
- Frontend: `BuildBotCard.tsx` (fast / slow / signal inputs), new `macdChart.ts` registered in
  `strategyCharts.ts`.
- Docs: `docs/trading-bots-roadmap.md`.
