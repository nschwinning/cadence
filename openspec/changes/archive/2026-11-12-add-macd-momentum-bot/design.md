## Context

Course Algo 10 waits for 50 prices, seeds EMA12 / EMA26 with the simple mean of the last 12 / 26 of
them, seeds the signal line with the first MACD, then updates all three per price
(α = 2 / (period + 1)). Entry: `prev_macd <= prev_signal and macd > signal` with `macd > 0`. Exits:
TP 0.5% / SL 0.5% only; drawdown 5%.

## Goals / Non-Goals

**Goals:** a faithful, deterministic, long-only port; preset; form; guide; roadmap.

**Non-Goals:** a MACD cross-down exit (the course has none); reusing the AI-portfolio technical
indicator MACD (different seeding; strategies stay self-contained like the other ports).

## Decisions

1. **`MacdMomentumParams`**: `fast_period` ≥ 2 (12), `slow_period` > `fast_period` (26),
   `signal_period` ≥ 2 (9), validated like the MA crossover periods.
2. **Replay with a fixed seed point**: the EMAs carry state, so the strategy replays the closes it
   is given. Seed at the first `slow_period` closes (slow EMA = their mean, fast EMA = mean of the
   last `fast_period` of them, signal = MACD), then update for every later close. This replaces the
   course's 50-price warm-up (which only exists to have enough prices to seed); after the replay
   the EMAs have converged, so the seed point does not change signals in practice.
   `required_history` = `3 × slow_period + signal_period` (87 for the defaults): enough bars after
   the seed for the signal EMA to settle, and fixed per params so each tick replays the same span.
3. **Cross on the latest bar only**: compare the previous bar's (MACD, signal) with the latest —
   the engine evaluates once per new bar, matching the course's per-price check.
4. **Holding → HOLD** (course exits only by TP/SL; engine owns them).
5. **Preset** `macd_momentum_algo10` (default): 12/26/9, TP 0.005, SL 0.005, DD 0.05.
6. **Frontend**: `BuildBotCard` MACD branch (Fast EMA, Slow EMA, Signal EMA; slow > fast enforced)
   with its own setters (`fast_period` / `slow_period` are also MA Crossover names); `macdChart.ts`
   plots synthetic price with MACD / signal on a second axis and the entry marker.

## Risks / Trade-offs

- Tight 0.5% / 0.5% brackets on 5-minute bars trade often — course recipe, user can retune.
- Seed point differs from the course's 50-price warm-up; negligible after convergence (documented).

## Migration Plan

None (additive).

## Open Questions

None.
