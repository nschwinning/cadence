## Context

Course Algo 12 builds 5-tick candles and computes ADX with **simple sums** (`np.convolve` with
ones): rolling `period` sums of TR / +DM / −DM → +DI, −DI → DX → ADX = mean of the last `period`
DX. Course Algo 15 computes "flexible" DI/DX over **all candles since start** (no ADX smoothing:
the value compared to the threshold is DX), enters long on close < rolling mean of typical prices
(its "VWAP"), takes profit at 0.5%, has no price stop, and exits a losing long when DX > 20 and
−DI > +DI. Cadence bars carry real OHLC, so both port directly on bars.

## Goals / Non-Goals

**Goals:** course-faithful ADX strategy; an opt-in ADX danger exit on the reversion bot that
reproduces Algo 15; both presets; form, guide, roadmap.

**Non-Goals:** Wilder-smoothed ADX (not what the course does); ADX as an entry filter on other
bots; the course short legs.

## Decisions

1. **Shared helpers** in `adx_trend.py`: `directional_movement(bars)` → per-bar (TR, +DM, −DM);
   `di_dx(tr, pdm, mdm)` → (+DI, −DI, DX) for one summed window (DX = 0 when +DI + −DI = 0 or
   ΣTR = 0). `adx_series` computes rolling-window DI/DX and ADX exactly as the course convolve.
2. **`AdxTrendParams`**: `period` ≥ 2 (10), `threshold` in (0, 100) (20); `required_history` =
   2 × `period` (period−1 diffs for the first DI window plus `period` DX values).
3. **Reversion ADX exit**: new fields `adx_exit` (False), `adx_lookback` ≥ 2 (20), `adx_threshold`
   in (0, 100) (20). When on, `required_history` = max(window, adx_lookback) — the lookback
   counts bars, as the course sums over its candles. The check runs
   first while holding, in both exit modes: close < `position.avg_price` and DX over the last
   `adx_lookback` bars > threshold and −DI > +DI → EXIT. **Lookback choice:** the course sums over
   *every* candle since start, which a fixed-history pure strategy cannot do; the preset uses 20,
   the same as its VWAP window. Recorded as the one non-literal value of the Algo 15 preset.
4. **Presets**: `adx_trend_algo12` (default) and `rolling_reversion_vwap_adx_algo15`
   (`average_type='typical'`, window 20, band, entry 0, exit 0.005, z 1.0/0.2, `exit_mode='bracket'`,
   `adx_exit=True`, lookback 20, threshold 20; TP 0.005, SL None, DD 0.05). Existing reversion
   presets are untouched (new fields default off; backend customized check compares parsed
   params, so defaults are equal).
5. **Frontend**: `BuildBotCard` gains an ADX branch (Period, Threshold) and, for reversion, an
   "ADX danger exit" checkbox revealing Lookback and Threshold; reversion sends the three ADX
   fields only when the filter is on (so non-ADX presets still compare equal). `adxChart.ts`
   plots a synthetic OHLC series' ADX with the threshold line and entry/exit markers.

## Risks / Trade-offs

- Simple-sum ADX reacts faster and noisier than Wilder's — faithful to the course.
- The Algo 15 lookback (20 vs unbounded) can differ from the course in long sessions; documented in
  the preset description.

## Migration Plan

None (additive). Ship with the normal deploy.

## Open Questions

None.
