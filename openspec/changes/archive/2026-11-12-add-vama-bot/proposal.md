## Why

Next on the strategy-bot roadmap (`docs/trading-bots-roadmap.md`, Tier 2 #10) is **VAMA**, course
Algo 30 — a moving average meant to adapt its speed to volatility. The course script's adaptation is
a no-op (it divides the current volatility by itself, so the smoothing is always the maximum, 0.20),
making it a plain EMA. The user chose to ship a genuinely adaptive VAMA **and** keep the course's
exact behaviour as a setting used by the Algo 30 preset.

## What Changes

- New strategy **VAMA** (`vama`), pure and long-only: a moving average updated as
  α·close + (1 − α)·previous. Enter long when the close is above the VAMA; exit when it falls to or
  below it. Short leg dropped.
- **Smoothing modes**:
  - *fixed* (`adaptive` off — the course): α = `alpha_max` (0.20), or `alpha_min` (0.02) when prices
    are flat;
  - *adaptive* (`adaptive` on — new): α = `alpha_max` × current volatility ÷ average volatility,
    clamped to [`alpha_min`, `alpha_max`]; current volatility = std of the last `lookback` closes,
    average volatility = mean of that std over the last `lookback` bars.
- Preset **VAMA (Algo 30)** — default: lookback 20, α 0.02–0.20, adaptive off, TP off, SL off,
  drawdown 5% (course has no price brackets).
- Build form inputs (incl. an "Adaptive smoothing" toggle), a strategy-guide illustration, roadmap
  update.
- No migration, no settings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: adds the VAMA strategy and its preset.

## Impact

- Backend: new `strategy_bots/vama.py`; `constants.py`, `registry.py`, `presets.py`.
- Frontend: `BuildBotCard.tsx` (lookback, α range, adaptive toggle), new `vamaChart.ts` registered in
  `strategyCharts.ts`.
- Docs: `docs/trading-bots-roadmap.md`.
