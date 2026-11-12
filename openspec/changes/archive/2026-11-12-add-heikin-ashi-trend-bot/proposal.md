## Why

Next on the strategy-bot roadmap (`docs/trading-bots-roadmap.md`, Tier 2 #7) is **Heikin-Ashi
Trend**, course Algo 11, with course Algo 37 as its volume-confirmed variant. Heikin-Ashi candles
smooth bar noise into clear green / red trend runs — a different trend read from the breakout,
band, ADX and MACD bots already shipped.

## What Changes

- New strategy **Heikin-Ashi Trend** (`heikin_ashi_trend`), pure and long-only: Heikin-Ashi candles
  built from the bars (path-dependent open, replayed over a fixed span). Enter on a green candle,
  exit on a red one.
- Optional **volume filter** (Algo 37): enter only when the latest bar's volume is above the
  `volume_window`-bar mean; also exit when volume fades to or below it. Off by default.
- Presets: **Heikin-Ashi Trend (Algo 11)** — default: filter off, TP 0.5%, SL 1%, drawdown 5%.
  **Heikin-Ashi + Volume (Algo 37)** — filter on, 20-bar window, TP off, SL off, drawdown 5% (the
  course has no price brackets).
- Build form inputs, a strategy-guide illustration, roadmap update.
- No migration, no settings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: adds the Heikin-Ashi Trend strategy and its two presets.

## Impact

- Backend: new `strategy_bots/heikin_ashi_trend.py`; `constants.py`, `registry.py`, `presets.py`.
- Frontend: `BuildBotCard.tsx` (volume filter checkbox + window), new `heikinAshiChart.ts`
  registered in `strategyCharts.ts`.
- Docs: `docs/trading-bots-roadmap.md`.
