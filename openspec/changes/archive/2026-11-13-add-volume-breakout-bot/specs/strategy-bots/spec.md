## ADDED Requirements

### Requirement: Volume Breakout strategy

The system SHALL provide a **Volume Breakout** strategy, registered alongside the existing
strategies. It SHALL be a pure, long-only signal generator that, given recent bars, the current
position, and its parameters, returns one of ENTER_LONG, EXIT, or HOLD together with a
human-readable reason, performing no I/O and holding no persisted state. Its `version` SHALL be
`spike`, `vroc` or `chaikin` (default `spike`). With fewer bars than the selected version needs
it SHALL signal HOLD. It SHALL never signal a short entry; take-profit, stop-loss and the drawdown
kill-switch stay with the engine.

**Spike version** (parameters `lookback` at least 3, default 30; `volume_window` at least 1,
default 20; `spike_multiplier` greater than 0, default 1.1). The prior range SHALL be the highest
and lowest close of the `lookback − 1` bars before the latest bar. A volume spike SHALL be the
latest bar's volume strictly above `spike_multiplier` × the mean volume of the latest
`volume_window` bars, the latest bar included. While flat, the strategy SHALL signal ENTER_LONG
when the latest close is strictly above the prior high with a volume spike. While holding, it
SHALL signal EXIT when the latest close is strictly below the prior low with a volume spike, and
HOLD otherwise.

**VROC version** (parameters `vroc_lookback` at least 1, default 5; `range_lookback` at least 2,
default 5; `vroc_threshold` default 40; `vroc_surge` default 70 and not below `vroc_threshold`;
`tight_range_pct` greater than 0, default 0.006; `prime_window` at least 1, default 10). The VROC
at a bar SHALL be (its volume − the volume `vroc_lookback` bars earlier) ÷ that earlier volume ×
100, undefined when the earlier volume is not positive. A bar SHALL **prime** when its VROC is
strictly above `vroc_threshold` and either its VROC is strictly above `vroc_surge` or the range
(highest − lowest close) of the `range_lookback` closes ending at it is strictly below
`tight_range_pct` × its close; the priming's range high SHALL be that highest close. While flat,
the strategy SHALL find the most recent priming bar among the `prime_window` bars before the
latest bar and SHALL signal ENTER_LONG when the latest close is strictly above its range high and
no close after the priming bar and before the latest bar was above it (the first breakout only);
otherwise HOLD. While holding, it SHALL signal EXIT when the latest bar's VROC is negative, and
HOLD otherwise.

**Chaikin version** (parameters `chaikin_fast` at least 1, default 3; `chaikin_slow` greater
than `chaikin_fast`, default 5). Each bar's money-flow multiplier SHALL be ((close − low) −
(high − close)) ÷ (high − low), or 0 when high equals low; the accumulation/distribution line SHALL
be the running sum of multiplier × volume over the bars provided. The oscillator SHALL be the
exponential moving average of that line over `chaikin_fast` bars minus the one over
`chaikin_slow` bars (smoothing 2 ÷ (span + 1), seeded with the first value), computed over the
bars provided so the result is deterministic. While flat, the strategy SHALL signal ENTER_LONG
when the previous bar's oscillator is at or below zero and the latest is strictly above zero.
While holding, it SHALL signal EXIT when the latest oscillator is strictly below zero, and HOLD
otherwise.

#### Scenario: Spike enters on a volume-confirmed breakout

- **WHEN** the Spike version is flat, the latest close is above the prior high and its volume is
  above `spike_multiplier` × the average volume
- **THEN** the strategy SHALL signal ENTER_LONG

#### Scenario: Spike ignores a breakout without volume

- **WHEN** the Spike version is flat and the latest close is above the prior high but its volume
  is not above `spike_multiplier` × the average volume
- **THEN** the strategy SHALL signal HOLD

#### Scenario: Spike exits on a volume-confirmed breakdown

- **WHEN** the Spike version holds a position and the latest close is below the prior low with a
  volume spike
- **THEN** the strategy SHALL signal EXIT

#### Scenario: VROC enters on the first breakout after priming

- **WHEN** the VROC version is flat, a bar within the priming window primed, and the latest
  close is the first close above that priming's range high
- **THEN** the strategy SHALL signal ENTER_LONG

#### Scenario: VROC ignores stale or missing priming

- **WHEN** the VROC version is flat and no bar within the priming window primed
- **THEN** the strategy SHALL signal HOLD even if the close breaks above an older range

#### Scenario: VROC does not re-enter on an already broken range

- **WHEN** the VROC version is flat and an earlier close after the priming bar already broke
  above its range high
- **THEN** the strategy SHALL signal HOLD

#### Scenario: VROC exits when volume momentum reverses

- **WHEN** the VROC version holds a position and the latest VROC is negative
- **THEN** the strategy SHALL signal EXIT

#### Scenario: Chaikin enters on a zero-line cross up

- **WHEN** the Chaikin version is flat, the previous oscillator is at or below zero and the
  latest is above zero
- **THEN** the strategy SHALL signal ENTER_LONG

#### Scenario: Chaikin exits below zero

- **WHEN** the Chaikin version holds a position and the latest oscillator is below zero
- **THEN** the strategy SHALL signal EXIT

#### Scenario: Insufficient history

- **WHEN** fewer bars than the selected version needs are available
- **THEN** the strategy SHALL signal HOLD

## MODIFIED Requirements

### Requirement: Bot preset catalog

The system SHALL maintain a fixed catalog of **bot presets**. Each preset SHALL have a
stable key, a display name, a short description, a reference to the course algorithm it
reproduces, the key of the registered strategy it uses, that strategy's parameters, and
the risk controls it applies — the take-profit and stop-loss thresholds (each either a
percentage or off) and the drawdown kill-switch limit. A preset SHALL NOT fix the
session's capital, traded assets, benchmark, label, or position-sizing settings; those
remain choices made when a session is created. Every preset's strategy parameters SHALL be
valid for its strategy. Each registered strategy SHALL have exactly one **default
preset**. The system SHALL let a client list the presets, and the listing SHALL report,
for each preset, all of the fields above and whether it is its strategy's default.

The catalog SHALL include these presets, reproducing the reference-course recipes:

- **MA Crossover (Algo 6)** — default for the moving-average crossover strategy: fast
  period 5, slow period 12; take-profit 1%, stop-loss 2%, drawdown limit 5%.
- **RSI Mean Reversion (Algo 16)** — default for the RSI mean-reversion strategy:
  period 14, oversold 30, exit level 50; take-profit 0.5%, stop-loss 1%, drawdown
  limit 5%.
- **Turtle Breakout (Algo 25)** — default for the Donchian range-breakout strategy:
  Turtle version, entry period 20, exit period 10; take-profit off, stop-loss off,
  drawdown limit 5%.
- **Smart Range Breakout (Algo 8)** — Donchian range-breakout strategy, Locked version,
  channel period 20, ATR padding multiplier 0.5; take-profit 0.5%, stop-loss 2%,
  drawdown limit 5%.
- **SMA Band Reversion (Algo 5)** — default for the Rolling-Average Reversion strategy:
  SMA average, window 20, band distance, entry threshold 1%, exit threshold 0.5%, revert
  exit; take-profit off, stop-loss 2%, drawdown limit 5%.
- **Z-Score Reversion (Algo 4)** — Rolling-Average Reversion strategy: SMA average,
  window 20, z-score distance, entry z 1.0, exit z 0.2, revert exit; take-profit off,
  stop-loss 2%, drawdown limit 5%.
- **Mean Cross Reversion (Algo 14)** — Rolling-Average Reversion strategy: SMA average,
  window 60, band distance with entry threshold 0 (bare cross), bracket exit;
  take-profit 0.5%, stop-loss 1%, drawdown limit 5%.
- **VWAP Cross Reversion (Algo 39)** — Rolling-Average Reversion strategy: volume-weighted
  average, window 60, band distance with entry threshold 0 (bare cross), bracket exit;
  take-profit 0.5%, stop-loss 1%, drawdown limit 5%.
- **SuperTrend (Algo 9)** — default for the ATR-Band Trend strategy: SuperTrend version,
  window 20, ATR multiplier 3; take-profit 0.5%, stop-loss 0.5%, drawdown limit 5%.
- **Keltner Breakout (Algo 21)** — ATR-Band Trend strategy, Keltner version, window 20, ATR
  multiplier 1, midline exit on; take-profit 0.5%, stop-loss 1%, drawdown limit 5% (the course
  script has no drawdown stop; 5% follows the catalog convention).
- **ADX Trend Strength (Algo 12)** — default for the ADX Trend Strength strategy: period 10,
  threshold 20; take-profit 0.5%, stop-loss 1%, drawdown limit 5%.
- **VWAP + ADX Reversion (Algo 15)** — Rolling-Average Reversion strategy: typical-price
  average, window 20, band distance with entry threshold 0 (bare cross), bracket exit, ADX danger
  exit on with lookback 20 and threshold 20; take-profit 0.5%, stop-loss off, drawdown limit 5%.
- **MACD Momentum (Algo 10)** — default for the MACD Momentum strategy: fast 12, slow 26, signal
  9; take-profit 0.5%, stop-loss 0.5%, drawdown limit 5%.
- **Heikin-Ashi Trend (Algo 11)** — default for the Heikin-Ashi Trend strategy: volume filter off;
  take-profit 0.5%, stop-loss 1%, drawdown limit 5%.
- **Heikin-Ashi + Volume (Algo 37)** — Heikin-Ashi Trend strategy with the volume filter on over a
  20-bar volume average; take-profit off, stop-loss off, drawdown limit 5%.
- **HMA Trend (Algos 19 / 26)** — default for the HMA Trend strategy: fast period 9, slow period
  21; take-profit 0.5%, stop-loss 1%, drawdown limit 5% (Algo 26 trades identically to Algo 19).
- **MA Ribbon (Algo 18)** — default for the MA Ribbon strategy: fast 5, mid 10, slow 20; take-profit
  0.5%, stop-loss 1%, drawdown limit 5%.
- **VAMA (Algo 30)** — default for the VAMA strategy: lookback 20, smoothing 0.02–0.20, adaptive
  smoothing off (reproducing the course script, whose smoothing is fixed at 0.20); take-profit off,
  stop-loss off, drawdown limit 5%.
- **Gradient Convergence (Algo 3)** — Rolling-Average Reversion strategy: SMA average, window 5,
  band distance with entry and exit thresholds 0 (buy below the 5-bar average, sell once back at
  or above it), revert exit; take-profit off, stop-loss off, drawdown limit 5%.
- **Price Velocity Reversal (Algo 48)** — default for the Price Velocity Reversal strategy: velocity
  threshold 0.2% per bar (the course's ₹2 move on its ₹1,000 simulated price); take-profit 0.5%,
  stop-loss 1%, drawdown limit 5%.
- **Trend Confirmation (Cadence)** — default for the Trend Confirmation strategy (Cadence's own
  recipe, not a course algorithm): SMA 20 / 50, MACD 12 / 26 / 9, RSI 14 entering between 50 and
  70 and exiting below 45, ROC and OBV legs off; take-profit 1%, stop-loss 1%, drawdown limit 5%.
- **Volume Spike (Algo 34)** — default for the Volume Breakout strategy: Spike version, lookback
  30, volume window 20, spike multiplier 1.1; take-profit off, stop-loss off, drawdown limit 5%
  (the course script has no drawdown stop; 5% follows the catalog convention).
- **Volume Spike — Simple (Algo 34)** — Volume Breakout strategy, Spike version, lookback 30,
  volume window 20, spike multiplier 1; take-profit off, stop-loss off, drawdown limit 5%.
- **VROC Breakout (Algo 46)** — Volume Breakout strategy, VROC version: VROC lookback 5, range
  lookback 5, VROC threshold 40, surge level 70, tight range 0.6%, priming window 10;
  take-profit 2%, stop-loss 1%, drawdown limit 5%.
- **Chaikin Oscillator (Algo 45)** — Volume Breakout strategy, Chaikin version: fast EMA 3, slow
  EMA 5; take-profit 0.6%, stop-loss 1.2%, drawdown limit 5%.

#### Scenario: List presets

- **WHEN** a client requests the preset catalog
- **THEN** the system SHALL return every preset with its key, display name, description,
  course reference, strategy key, strategy parameters, take-profit, stop-loss, drawdown
  limit, and whether it is its strategy's default

#### Scenario: One default preset per strategy

- **WHEN** a client requests the preset catalog
- **THEN** every registered strategy SHALL have exactly one preset marked as its default

#### Scenario: Preset parameters are valid for their strategy

- **WHEN** the preset catalog is loaded
- **THEN** every preset's strategy parameters SHALL validate against its strategy's
  parameter schema

#### Scenario: Rolling-Average Reversion course presets listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the four Rolling-Average Reversion presets for Algos 5, 4, 14
  and 39, with the Algo 5 preset marked as the strategy's default

#### Scenario: ATR-Band Trend course presets listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the SuperTrend (Algo 9) and Keltner Breakout (Algo 21) presets for the
  ATR-Band Trend strategy, with the Algo 9 preset marked as the strategy's default

#### Scenario: ADX course presets listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the ADX Trend Strength (Algo 12) preset as the ADX strategy's
  default and the VWAP + ADX Reversion (Algo 15) preset for the Rolling-Average Reversion
  strategy

#### Scenario: MACD course preset listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the MACD Momentum (Algo 10) preset as the MACD Momentum strategy's
  default

#### Scenario: Heikin-Ashi course presets listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the Heikin-Ashi Trend (Algo 11) preset as the Heikin-Ashi strategy's
  default and the Heikin-Ashi + Volume (Algo 37) preset

#### Scenario: HMA course preset listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the HMA Trend (Algos 19 / 26) preset as the HMA Trend strategy's
  default

#### Scenario: MA Ribbon course preset listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the MA Ribbon (Algo 18) preset as the MA Ribbon strategy's default

#### Scenario: VAMA course preset listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the VAMA (Algo 30) preset as the VAMA strategy's default, with adaptive
  smoothing off

#### Scenario: Price Velocity Reversal course preset listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the Price Velocity Reversal (Algo 48) preset as the strategy's default

#### Scenario: Gradient Convergence preset listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the Gradient Convergence (Algo 3) preset for the Rolling-Average
  Reversion strategy

#### Scenario: Trend Confirmation preset listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the Trend Confirmation (Cadence) preset as the Trend Confirmation
  strategy's default

#### Scenario: Volume Breakout course presets listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the Volume Spike (Algo 34), Volume Spike — Simple (Algo 34), VROC
  Breakout (Algo 46) and Chaikin Oscillator (Algo 45) presets for the Volume Breakout strategy,
  with the Volume Spike (Algo 34) preset marked as the strategy's default
