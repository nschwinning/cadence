## Why

Tiers 1–3 of the strategy-bot roadmap (`docs/trading-bots-roadmap.md`) are shipped. Tier 4 holds
the composite bots; the first is **Volatility Regime Switcher** (#15, course Algo 20). Every
catalog strategy today is either trend-following or mean-reverting regardless of conditions; this
one measures volatility and switches between a trend rule and a reversion rule, giving manual users
and the AI orchestrator a regime-aware option.

## What Changes

- New strategy **Volatility Regime Switcher** (`volatility_regime`), pure, stateless and long-only:
  - ATR is the course proxy — the mean absolute close-to-close change over the latest
    `atr_window` closes (as the ATR-Band bot uses).
  - **Baseline:** the course freezes its baseline from the first 20 prices after start; Cadence is
    stateless, so by decision the baseline is the **average of the rolling ATR over the latest
    `baseline_bars` bars** (default 100).
  - **Regime (course mapping, by decision):** ATR at or below the baseline → **trend**; above →
    **reversion**.
  - **Trend:** enter long when the close is above HL2 — the midpoint of the highest and lowest of
    the latest `atr_window` closes; exit when it falls below HL2.
  - **Reversion:** enter long when the close is below SMA(`sma_period`) × (1 − `reversion_deviation`);
    exit when it is back at or above the SMA.
  - Exits follow the **current** regime (as the course does); course short legs are dropped.
    Take-profit, stop-loss and the drawdown kill-switch stay with the engine.
- One catalog preset: **Volatility Regime Switcher (Algo 20)** — default: ATR window 20, SMA 20,
  baseline 100 bars, deviation 0; take-profit 0.5%, stop-loss 1%, drawdown 5% (the course has no
  drawdown stop; 5% catalog convention).
- Build form inputs; strategy-guide illustration chart.
- Roadmap document: Volatility Regime Switcher shipped; shipped count updated.
- No migration (`strategy_key` is free text), no new settings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: adds the Volatility Regime Switcher strategy and its preset to the catalog.

## Impact

- Backend: new `strategy_bots/volatility_regime.py` (reuses `atr_band_trend.mean_abs_close_change`);
  `constants.py`, `registry.py`, `presets.py`.
- Frontend: `pages/bots/BuildBotCard.tsx`, new `pages/bots/volatilityRegimeChart.ts` registered in
  `strategyCharts.ts`.
- Docs: `docs/trading-bots-roadmap.md`.
- The orchestrator's preset catalog (and the Orchestrators page's preset list) gains the preset.
