## Why

Tiers 1 and 2 of the strategy-bot roadmap (`docs/trading-bots-roadmap.md`) are shipped. Tier 3 has
one bot: **Volume Breakout** (#14), the volume-confirmed family behind course Algo 34 (Volume
Spike), Algo 46 (Volume Rate of Change) and Algo 45 (Chaikin Oscillator). None of the catalog's
strategies trade on volume as the primary signal, so this gives manual users and the AI
orchestrator (which deploys any catalog preset) a volume-driven option. The roadmap's data caveat
— Algo 45 fakes highs and lows with random numbers — is resolved by Cadence's real OHLCV bars.

## What Changes

- New strategy **Volume Breakout** (`volume_breakout`), pure, stateless and long-only, with a
  `version` selector:
  - **Spike** (Algo 34): enter when the close breaks above the highest close of the prior
    `lookback − 1` bars while volume exceeds `spike_multiplier` × the average volume of the
    latest `volume_window` bars. The course only prints signals and has no exit; by decision its
    "short breakout" (close below the prior low with a volume spike) becomes the long **exit**,
    like the Turtle channel.
  - **VROC** (Algo 46): volume rate of change `(V − V[−n]) / V[−n] × 100`. A bar **primes** when
    VROC exceeds `vroc_threshold` and the latest `range_lookback`-bar close range is tighter than
    `tight_range_pct` of the close (or VROC exceeds `vroc_surge`). Enter on the first close above
    a priming bar's range high, if that priming is at most `prime_window` bars old (the course
    remembers it indefinitely; Cadence is stateless, so by decision it looks back 10 bars). Exit
    when VROC turns negative.
  - **Chaikin** (Algo 45): accumulation/distribution line from real high/low/close/volume;
    oscillator = EMA(`chaikin_fast`) − EMA(`chaikin_slow`) of it, using **proper converged EMAs**
    (by decision; the course truncates them to the last 3 / 5 values). Enter when the oscillator
    crosses above zero; exit when it falls below zero.
  - Course short legs are dropped (long-only); take-profit, stop-loss and the drawdown
    kill-switch stay with the engine.
- Four catalog presets: **Volume Spike (Algo 34)** — default (multiplier 1.1, Algo 34 b);
  **Volume Spike — Simple (Algo 34)** (multiplier 1, Algo 34 a); **VROC Breakout (Algo 46)**;
  **Chaikin Oscillator (Algo 45)**. Course take-profit / stop-loss values; drawdown 5% (the 5%
  catalog convention where the course has none).
- Build form: version-aware parameter inputs; strategy guide: an illustration chart.
- Roadmap document: Volume Breakout shipped (15 of 16); Tier 3 complete.
- No migration (`strategy_key` is free text), no new settings.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `strategy-bots`: adds the Volume Breakout strategy and its four presets to the catalog.

## Impact

- Backend: new `strategy_bots/volume_breakout.py`; `constants.py` (key, display name,
  explanation), `registry.py`, `presets.py`; reuses `technical_indicators/series.ema`.
- Frontend: `pages/bots/BuildBotCard.tsx` (inputs, payload, validation), new
  `pages/bots/volumeBreakoutChart.ts` registered in `strategyCharts.ts`.
- Docs: `docs/trading-bots-roadmap.md`.
- The orchestrator's preset catalog (and the Orchestrators page's preset list) grows by four
  presets automatically.
