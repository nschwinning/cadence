## Context

Strategies implement the pure `Strategy.evaluate(bars, position, params)` contract
(`strategy_bots/strategy.py`), declare `required_history` via their params, and are registered in
`registry.py`; presets live in `presets.py` and flow to the build form and the orchestrator via
`GET /bots/presets`. The Donchian port established the pattern for a version selector inside one
strategy and the course's close-based ATR (mean absolute close-to-close change). Course scripts
read a single price stream, so both Algo 9 and Algo 21 work on closes only.

## Goals / Non-Goals

**Goals:** a course-faithful, long-only port of Algo 9 and Algo 21 as one strategy with two
presets; form inputs and a guide illustration; roadmap updated.

**Non-Goals:** canonical OHLC SuperTrend (true range, bar hl2) — the course uses closes; short
legs; the Keltner "flip to short"; new engine features.

## Decisions

1. **One strategy, `version` selector** (`supertrend` | `keltner`), `AtrBandTrendParams`
   (`extra='forbid'` like the other params): `window` ≥ 2 (20), `atr_mult` > 0 (3.0),
   `exit_on_midline` (True). Off-version fields keep defaults. *Alternative:* two strategies —
   rejected; the roadmap groups them as one "midline ± k·ATR" family and the Donchian precedent
   uses versions.
2. **ATR** = mean of |closeᵢ − closeᵢ₋₁| over the window (course `calc_atr`), shared helper.
3. **SuperTrend replay**: SuperTrend is path-dependent (band ratchet + previous line). The
   strategy replays every full window in the bars it is given, oldest first, carrying
   `trend`, previous bands and previous line exactly like the course loop. `required_history`
   = `3 × window` so the ratchet has two windows to settle; the engine always fetches that many
   bars, making the replay deterministic per tick. While flat: ENTER_LONG iff trend up and
   close > line. While holding: HOLD (course exits only by TP/SL; engine owns those).
4. **Keltner**: mid = mean of the last `window` closes (current bar included, as in the course),
   bands mid ± `atr_mult`·ATR; `required_history` = `window`. Flat: ENTER_LONG iff close > upper.
   Holding: EXIT iff `exit_on_midline` and close < mid. The course "flip on opposite break" is
   subsumed (lower band < mid) and the short leg dropped.
5. **Presets** in `presets.py`: `atr_band_supertrend_algo9` (default; 20 / 3.0; TP 0.005, SL
   0.005, DD 0.05) and `atr_band_keltner_algo21` (keltner, 20 / 1.0, midline exit; TP 0.005,
   SL 0.01, DD 0.05 — course has none, catalog convention).
6. **Frontend**: `BuildBotCard` gains an `isAtrBand` branch — version select, window, ATR
   multiplier (step 0.1) and, for Keltner, a "Exit below the midline" checkbox; payload
   `{version, window, atr_mult, exit_on_midline}`; presets prefill as for other strategies.
   `atrBandChart.ts` draws a synthetic price path with the bands and entry/exit markers, registered
   in `strategyCharts.ts` so the guide pages render it.

## Risks / Trade-offs

- Close-only bands are a faithful but simplified port; a later OHLC variant could be added as
  another version without breaking presets.
- 0.5% TP/SL brackets on daily bars rarely trigger intrabar-accurately; same caveat as existing
  presets (engine evaluates on tick bars).

## Migration Plan

None (additive; `strategy_key` is free text). Ship with the normal deploy.

## Open Questions

None.
