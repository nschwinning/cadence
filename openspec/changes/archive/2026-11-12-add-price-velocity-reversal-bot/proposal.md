## Why

Next on the strategy-bot roadmap (`docs/trading-bots-roadmap.md`, Tier 2 #11) is **Price Velocity
Reversal**, course Algo 48 (file mislabelled `algo 49.py`): it buys a sharp drop that is starting to
slow down and sells as soon as price turns up — a short-horizon reversal bot unlike the trend and
band bots already shipped.

## What Changes

- New strategy **Price Velocity Reversal** (`price_velocity_reversal`), pure and long-only:
  velocity = latest close's % change, acceleration = velocity − previous velocity. Enter long when
  velocity < −threshold and acceleration > 0; exit when velocity turns positive. Short leg dropped.
- **Deliberate adaptation (user decision):** the course threshold is an absolute ₹2 move on a
  ₹1,000 simulated price; Cadence trades stocks at any price, so velocity is measured in percent and
  the preset uses 0.2% (₹2 / ₹1,000).
- Preset **Price Velocity Reversal (Algo 48)** — default: 0.2%, TP 0.5%, SL 1%, drawdown 5%.
- Build form input, a strategy-guide illustration, roadmap update.
- No migration, no settings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: adds the Price Velocity Reversal strategy and its preset.

## Impact

- Backend: new `strategy_bots/price_velocity_reversal.py`; `constants.py`, `registry.py`,
  `presets.py`.
- Frontend: `BuildBotCard.tsx` (threshold input in percent), new `velocityChart.ts` registered in
  `strategyCharts.ts`.
- Docs: `docs/trading-bots-roadmap.md`.
