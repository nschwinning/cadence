## Context

Course Algo 33 (`Algo 33.py`, plus a Tkinter calculator that shows the same formulas): reads
whole-rupee prices; Δ = (curr − prev) ÷ prev; Gaussian likelihoods with μ = {UP +0.001, FLAT 0,
DOWN −0.001}, σ = {UP 0.002, FLAT 0.0008, DOWN 0.002}; posterior = prior × L normalised (uniform if
the sum is 0); prior = previous posterior for the whole run; MAP with p ≥ 0.6 → LONG (UP) / SHORT
(DOWN), FLAT or p < 0.6 → NONE. It only logs to CSV — no position handling, exit, bracket or
drawdown stop.

User decisions: replay the last 20 bars; exit on the SHORT signal; no bracket, 5% drawdown.

## Goals / Non-Goals

**Goals:** one `bayesian_trend` strategy, one preset, form inputs, guide chart; roadmap complete.

**Non-Goals:** a hidden-Markov transition model (regime stickiness); fitting μ/σ from data;
persisting the posterior between ticks.

## Decisions

1. **`BayesianTrendParams`** (`extra='forbid'`): `drift` 0.001, `trend_sigma` 0.002, `flat_sigma`
   0.0008 (all > 0), `threshold` 0.6 (1/3 < t < 1 — below 1/3 the MAP always qualifies),
   `replay_bars` 20 (≥ 1). The course's μ/σ are symmetric for UP/DOWN, so one `drift` and one
   `trend_sigma` express them exactly with fewer fields.
2. **Required history** = `replay_bars + 1` closes (N returns).
3. **Log-space update**: keep log-posteriors, add each log-likelihood, renormalise with
   log-sum-exp. Identical to the course maths where it does not underflow; where the course would
   fall back to uniform (every likelihood 0 in floating point), this keeps the correct ordering.
4. **No rounding**: real closes; a non-positive previous close skips that return (guard only).
5. **MAP ties** resolve UP → FLAT → DOWN (course dict order with `max`).
6. **Signals**: flat → ENTER_LONG iff MAP = UP and p ≥ threshold; holding → EXIT iff MAP = DOWN and
   p ≥ threshold; else HOLD. Reason shows the three posteriors.
7. **Preset** `bayesian_trend_algo33` (default): course parameters, 20 bars; TP None, SL None,
   DD 0.05.
8. **Frontend**: five inputs (drift / σs in percent, threshold as a probability, replay bars);
   `bayesianChart.ts` plots a synthetic close with the three posteriors as stacked areas on a
   0–1 axis, the threshold dashed, and entry/exit marks — a TS mirror of the update.

## Risks / Trade-offs

- Without state transitions the posterior hardens within the window; the 20-bar replay bounds how
  long it takes to flip after a trend change.
- The course's μ/σ were tuned to the simulator's tick returns; on 5-minute equity bars they are
  plausible but not fitted. Calm names will sit in FLAT and rarely trade.

## Migration Plan

None (additive).

## Open Questions

None.
