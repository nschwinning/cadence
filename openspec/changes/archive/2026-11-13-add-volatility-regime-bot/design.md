## Context

Course Algo 20 (file header says "Algo 21"): close-only feed; ATR = mean absolute price change over
20 prices; `ATR_base` computed once from the 20-price warm-up; regime TREND when ATR ≤ base, else
REVERSION; TREND enters on price vs HL2 (mid of the 20-price range, current included) and exits on
the opposite cross; REVERSION enters on price < SMA20 × (1 − dev) (dev 0) and exits at ≥ SMA; exits
use the current regime; TP 0.5%, SL 1% (comment says 0.1%, the value is 0.010); no drawdown stop.

User decisions: rolling-average baseline; course regime mapping; course legs inline.

## Goals / Non-Goals

**Goals:** one `volatility_regime` strategy, one preset, form inputs, guide chart.

**Non-Goals:** composing arbitrary catalog strategies; persisting the start-up baseline;
remembering the regime a position was opened in.

## Decisions

1. **`VolatilityRegimeParams`** (`extra='forbid'`): `atr_window` 20 (≥ 2), `sma_period` 20 (≥ 2),
   `baseline_bars` 100 (≥ 2), `reversion_deviation` 0.0 (≥ 0, < 1). Names are unique in the catalog
   so presets and the form never collide.
2. **Required history** = `max(baseline_bars + atr_window − 1, sma_period)` = 119 by default — every
   ATR in the baseline has its full window.
3. **ATR** reuses `atr_band_trend.mean_abs_close_change` (same course proxy). The rolling ATRs are
   computed once per evaluation from the closes (O(n·window), n ≈ 120 — negligible).
4. **Ties:** ATR equal to the baseline is trend (course `<=`); flat prices (ATR 0 = baseline) are
   trend, where close == HL2 holds.
5. **Preset** `volatility_regime_algo20` (default): 20 / 20 / 100 / 0; TP 0.005, SL 0.01, DD 0.05.
6. **Frontend**: four number inputs (deviation in percent); `volatilityRegimeChart.ts` shades the
   calm/volatile regimes over a synthetic series with HL2 and SMA lines and marks entries/exits,
   mirroring the rules in a small TS helper.

## Risks / Trade-offs

- The 100-bar baseline spans the overnight gap on 5-minute bars; the gap is one close-to-close
  change among ~100 and only nudges the baseline.
- Exits follow the current regime: a trend entry can be closed by the reversion exit if volatility
  rises — course behaviour, and unavoidable statelessly.

## Migration Plan

None (additive).

## Open Questions

None.
