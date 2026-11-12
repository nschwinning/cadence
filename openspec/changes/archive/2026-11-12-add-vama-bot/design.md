## Context

Course Algo 30: keeps the latest 20 prices; `compute_alpha` sets `avg_vol = vol` so
`raw_alpha = vol / avg_vol = 1`, clamped to [0.02, 0.20] → α = 0.20 (0.02 if `vol == 0`); VAMA starts
at the 20th price and updates `α·p + (1 − α)·prev`. Long when price > VAMA, exit when price ≤ VAMA;
no TP/SL; drawdown 5%.

## Goals / Non-Goals

**Goals:** an honest adaptive VAMA plus an exact course mode; the course preset; form; guide; roadmap.

**Non-Goals:** other adaptive-MA families (KAMA, FRAMA); the short leg.

## Decisions

1. **`VamaParams`**: `lookback` ≥ 2 (20), `alpha_min` (0.02) < `alpha_max` (0.20), both in (0, 1],
   `adaptive` (False — defaults match the course).
2. **Volatility** = population standard deviation (`np.std`, as the course) of the latest `lookback`
   closes. Adaptive: average volatility = mean of that value over the latest `lookback` bars;
   α = clamp(`alpha_max` × current / average); average 0 → `alpha_min`. Ratio scaled by `alpha_max`
   so that "normal" volatility gives the course's 0.20 and calmer markets slow the average down.
3. **Replay**: VAMA is path-dependent. It starts at the first bar where α is defined (bar
   `lookback` for fixed, `2·lookback − 1` for adaptive) at that bar's close, then updates per bar.
   `required_history` = `4 × lookback` (fixed) or `5 × lookback` (adaptive) — at least two full
   `lookback` spans of updates after the start so the start point has negligible influence at
   α ≥ ~0.1 (documented: at α_min = 0.02 convergence is slower; acceptable, the bands are relative).
4. **Signals**: flat → ENTER_LONG iff close > VAMA; holding → EXIT iff close ≤ VAMA.
5. **Preset** `vama_algo30` (default): lookback 20, α 0.02–0.20, adaptive False; TP None, SL None,
   DD 0.05.
6. **Frontend**: VAMA branch — Lookback, α min, α max (step 0.01), "Adaptive smoothing" checkbox;
   payload always sends all five fields (preset has all five). `vamaChart.ts` plots a synthetic close
   with fixed and adaptive VAMA lines and the entry/exit of the fixed one.

## Risks / Trade-offs

- With adaptive smoothing, calm periods (α → α_min) make the line very slow; the clamp bounds it.
- No price brackets in the course recipe: exits rely on the VAMA cross and the drawdown stop.

## Migration Plan

None (additive).

## Open Questions

None.
