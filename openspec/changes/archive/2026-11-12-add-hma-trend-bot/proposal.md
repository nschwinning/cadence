## Why

Next on the strategy-bot roadmap (`docs/trading-bots-roadmap.md`, Tier 2 #8) is **HMA Trend**,
course Algo 19 (Algo 26 trades identically — its "news" module only perturbs the simulated price
feed). The Hull Moving Average follows price with little lag, giving a faster trend-following bot
than the SMA/EMA-based ones already shipped.

## What Changes

- New strategy **HMA Trend** (`hma_trend`), pure and long-only: fast and slow **proper** Hull Moving
  Averages of the close (WMA over √n of 2·WMA(n/2) − WMA(n)). Enter long when the fast HMA is above
  the slow one and rising; exit on a trend reversal (fast below slow and falling). Short leg dropped.
- **Deliberate deviation (user decision):** the course's `hull_ma` skips the final √n smoothing
  because of a bug (it smooths an array of one repeated value); the bot uses the proper HMA, so its
  signals are smoother and slightly later than the script's.
- Preset **HMA Trend (Algos 19 / 26)** — default: 9 / 21, TP 0.5%, SL 1%, drawdown 5%.
- Build form inputs, a strategy-guide illustration, roadmap update.
- No migration, no settings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: adds the HMA Trend strategy and its preset.

## Impact

- Backend: new `strategy_bots/hma_trend.py`; `constants.py`, `registry.py`, `presets.py`.
- Frontend: `BuildBotCard.tsx` (fast / slow HMA inputs), new `hmaChart.ts` registered in
  `strategyCharts.ts`.
- Docs: `docs/trading-bots-roadmap.md` (also noting Algo 26 = Algo 19).
