## Why

Tier 1 of the strategy-bot roadmap (`docs/trading-bots-roadmap.md`) has one bot left:
**ATR-Band Trend**, the "midline ± k·ATR" trend family behind course Algo 9 (SuperTrend) and
Algo 21 (Keltner Volatility Breakout). Shipping it completes Tier 1 and gives manual users and
the AI orchestrator (which deploys only catalog presets) a volatility-band trend-following
option alongside the existing breakout and mean-reversion bots.

## What Changes

- New strategy **ATR-Band Trend** (`atr_band_trend`), pure and long-only, with a `version`
  selector:
  - **SuperTrend** (Algo 9): rolling window of closes, mid-range ± `atr_mult`·ATR bands that only
    tighten while the trend persists; trend is up while the close stays above the previous
    SuperTrend line. Enter long when the trend is up and the close is above the SuperTrend line;
    while holding, all exits are left to the engine's take-profit / stop-loss bracket and
    drawdown kill-switch (the course exits only via TP/SL).
  - **Keltner** (Algo 21): SMA(`window`) ± `atr_mult`·ATR. Enter long when the close breaks above
    the upper band; exit when the close falls back below the SMA (`exit_on_midline`, on by
    default), plus the engine bracket.
  - ATR is the course's mean absolute close-to-close change over the window. Course short legs
    and the Keltner "flip to short" are dropped (long-only).
- Two catalog presets: **SuperTrend (Algo 9)** — default: window 20, multiplier 3, TP 0.5%,
  SL 0.5%, drawdown 5%; **Keltner Breakout (Algo 21)**: window 20, multiplier 1, midline exit
  on, TP 0.5%, SL 1%, drawdown 5% (the course script has no drawdown stop; 5% is the catalog
  convention).
- Build form: version-aware parameter inputs; strategy guide: an illustration chart.
- Roadmap document updated: Donchian, Rolling-Average Reversion and ATR-Band Trend marked
  shipped; Tier 1 complete.
- No migration (`strategy_key` is free text), no new settings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: adds the ATR-Band Trend strategy and its two presets to the catalog.

## Impact

- Backend: new `strategy_bots/atr_band_trend.py`; `constants.py` (key, display name,
  explanation), `registry.py`, `presets.py`.
- Frontend: `pages/bots/BuildBotCard.tsx` (inputs + payload + validation), new
  `pages/bots/atrBandChart.ts` registered in `strategyCharts.ts`.
- Docs: `docs/trading-bots-roadmap.md`.
- The orchestrator's preset catalog grows by two presets automatically.
