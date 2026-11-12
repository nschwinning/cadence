## Context

Course Algo 19 (and the identical Algo 26) computes `hull_ma(prices, n)`: `2·WMA(n//2) − WMA(n)` of
the latest prices, then `wma(np.array([hull] * int(sqrt(n))), int(sqrt(n)))` — a weighted mean of
one repeated value, i.e. the raw value. Entry: fast > slow and fast slope > 0. Exit: reversal (fast
< slow and slope < 0) or TP 0.5% / SL 1%; drawdown 5%. Fast 9, slow 21.

## Goals / Non-Goals

**Goals:** a long-only HMA trend bot with the proper Hull MA (user decision), the course entry /
reversal-exit rules and preset; form; guide; roadmap.

**Non-Goals:** reproducing the course's missing smoothing; the short leg.

## Decisions

1. **Proper HMA** (`hma(closes, n)`): for each of the latest ⌊√n⌋ bars compute the raw Hull value
   `2·WMA(⌊n/2⌋) − WMA(n)` of the closes up to that bar, then WMA over those ⌊√n⌋ raw values.
   `WMA(m)` weights 1…m, latest heaviest (course `wma`). Needs `n + ⌊√n⌋ − 1` closes.
2. **Slope** = fast HMA now − fast HMA one bar earlier (course `prev_fast` on the series without the
   latest price); needs one more bar.
3. **`HmaTrendParams`**: `fast_period` ≥ 2 (9), `slow_period` > `fast_period` (21);
   `required_history` = `slow_period + ⌊√slow_period⌋` (25 for the defaults) — covers both HMAs and
   the slope.
4. **Signals**: flat → ENTER_LONG iff fast > slow and slope > 0; holding → EXIT iff fast < slow and
   slope < 0, else HOLD.
5. **Preset** `hma_trend_algo19` (default, course_ref "Algos 19, 26"): 9 / 21; TP 0.005, SL 0.01,
   DD 0.05. One preset because the two scripts are identical.
6. **Frontend**: `BuildBotCard` HMA branch (Fast HMA, Slow HMA; slow > fast) with its own setters
   (`fast_period` / `slow_period` are also MA Crossover names); `hmaChart.ts` plots a synthetic close
   with both HMAs and entry / exit markers.

## Risks / Trade-offs

- Signals differ from the course script (smoother, later) — accepted; the script's indicator is
  not an HMA.

## Migration Plan

None (additive).

## Open Questions

None.
