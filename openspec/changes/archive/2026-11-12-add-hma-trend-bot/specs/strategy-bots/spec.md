## ADDED Requirements

### Requirement: HMA Trend strategy

The system SHALL provide an **HMA Trend** strategy, registered alongside the existing strategies.
It SHALL be a pure, long-only signal generator that, given recent bars, the current position, and
its parameters, returns one of ENTER_LONG, EXIT, or HOLD together with a human-readable reason,
performing no I/O and holding no persisted state. Its parameters SHALL be a `fast_period` (at
least 2, default 9) and a `slow_period` (strictly greater than `fast_period`, default 21).

The strategy SHALL use the Hull Moving Average of the closes. For a period n, WMA(m) is the
linearly weighted mean of the latest m values (weights 1 … m, the latest weighted most); the raw
Hull value at a bar is 2 × WMA(⌊n / 2⌋) − WMA(n) of the closes up to that bar, and HMA(n) is the
WMA over ⌊√n⌋ of the raw Hull values of the latest ⌊√n⌋ bars. The fast HMA's **slope** is its
latest value minus its value on the previous bar.

While flat, the strategy SHALL signal ENTER_LONG when the fast HMA is strictly above the slow HMA
and the slope is strictly positive. While holding, it SHALL signal EXIT on a trend reversal — the
fast HMA strictly below the slow HMA with a strictly negative slope — and HOLD otherwise
(take-profit, stop-loss and the drawdown kill-switch remain the engine's). With fewer bars than it
needs it SHALL signal HOLD. It SHALL never signal a short entry.

#### Scenario: Rising fast HMA above the slow HMA enters

- **WHEN** the strategy is flat, the fast HMA is above the slow HMA and rising
- **THEN** it SHALL signal ENTER_LONG

#### Scenario: Fast HMA above but falling is not entered

- **WHEN** the strategy is flat and the fast HMA is above the slow HMA but falling
- **THEN** it SHALL signal HOLD

#### Scenario: Trend reversal exits

- **WHEN** the strategy holds and the fast HMA is below the slow HMA and falling
- **THEN** it SHALL signal EXIT

#### Scenario: No reversal holds

- **WHEN** the strategy holds and the fast HMA is below the slow HMA but rising
- **THEN** it SHALL signal HOLD

#### Scenario: Insufficient history

- **WHEN** fewer bars than the strategy needs are available
- **THEN** it SHALL signal HOLD

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

