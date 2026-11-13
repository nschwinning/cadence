## Context

Roadmap #14 folds three course scripts into one volume-driven strategy, like the versioned
Donchian and ATR-Band bots. Course scripts read a simulated single price + volume feed:

- **Algo 34 a / b** (Volume Spike): 30-tick deque; prior high/low over the 29 earlier prices;
  spike = volume > mean(last 20 volumes, current included) × multiplier (a: 1, b: 1.1). Prints
  long/short "breakouts" only — no exit, TP/SL or drawdown.
- **Algo 46** (VROC): VROC over 6 volumes `(v[-1] − v[0]) / v[0] × 100`; when flat and not primed,
  VROC > 40 and (5-price range < 0.6% of close or VROC > 70) primes and remembers the range; a
  later close above the range high goes long. Exit: TP 2%, SL 1%, or VROC < 0; drawdown 5%.
- **Algo 45** (Chaikin): ADL from **random** fake highs/lows; EMA(3) − EMA(5) computed over only
  the last 3 / 5 ADL values; long on the oscillator crossing above 0, exit on TP 0.6%, SL 1.2% or
  oscillator < 0.

User decisions: Spike exits on the course's short-breakout condition; VROC priming may be at most
10 bars old; Chaikin uses proper converged EMAs.

## Goals / Non-Goals

**Goals:** one `volume_breakout` strategy with three versions, four presets, form inputs, guide
chart. **Non-Goals:** short legs; per-bot timeframes; volume-data quality checks beyond guarding
non-positive volumes.

## Decisions

1. **`VolumeBreakoutParams`** (`extra='forbid'`, version-prefixed names where they could collide):
   `version` ∈ {spike, vroc, chaikin}; Spike `lookback` 30 (≥ 3), `volume_window` 20 (≥ 1),
   `spike_multiplier` 1.1 (> 0); VROC `vroc_lookback` 5, `range_lookback` 5 (≥ 2),
   `vroc_threshold` 40, `vroc_surge` 70 (≥ threshold), `tight_range_pct` 0.006 (> 0, < 1),
   `prime_window` 10; Chaikin `chaikin_fast` 3 < `chaikin_slow` 5. All fields always present
   (like the Donchian / ATR-Band versions) so presets and the form round-trip.
2. **Required history** per version: Spike `max(lookback, volume_window)`; VROC
   `prime_window + max(vroc_lookback, range_lookback − 1) + 1` (the oldest candidate priming bar
   needs its VROC and range) = 16; Chaikin `3 × chaikin_slow + 1` = 16 (EMAs start at the first
   bar provided and converge over a fixed span, as for MACD).
3. **Spike** uses closes for the prior range (course-literal: one price per tick). Exit mirrors
   entry: close below the prior low **with** a spike.
4. **VROC stateless priming**: scan bars `n − 1 − prime_window … n − 2` for the most recent priming
   bar `p`; enter iff `close[n−1] > range_high(p)` and no close in `p+1 … n−2` exceeded it. The
   "first breakout only" rule replaces the course's reset-on-exit, so a bot that exited is not
   re-entered on the same priming. Course difference: the course keeps the *first* priming until
   it trades; Cadence uses the most recent within the window. Non-positive earlier volume → VROC
   undefined (no priming; while holding, HOLD).
5. **Chaikin** ADL is summed from the first bar provided; the oscillator is offset-invariant (EMA
   weights sum to 1), so the starting point does not matter. EMAs via the shared
   `technical_indicators.series.ema` (`adjust=False`).
6. **Presets**: `volume_spike_algo34` (default; 30 / 20 / 1.1; TP off, SL off, DD 5%),
   `volume_spike_simple_algo34` (multiplier 1), `vroc_breakout_algo46` (TP 2%, SL 1%, DD 5%),
   `chaikin_oscillator_algo45` (3 / 5; TP 0.6%, SL 1.2%, DD 5%).
7. **Frontend**: a version select with per-version fields, preset routing by `strategy_key` as for
   the other versioned strategies; `volumeBreakoutChart.ts` illustrates the Spike version (price
   with the prior-high channel above volume bars, a volume-confirmed breakout marked).

## Risks / Trade-offs

- 5-minute volume follows an intraday U-shape (open/close heavy); Spike and VROC will fire more
  around the open and close. Course-literal; documented in the explanation.
- VROC's exit on any negative bar-to-bar volume change is very noisy; kept course-literal with
  the 2% / 1% bracket.
- Chaikin's 3 / 5 EMAs are short; the zero line will be crossed often.

## Migration Plan

None (additive).

## Open Questions

None.
