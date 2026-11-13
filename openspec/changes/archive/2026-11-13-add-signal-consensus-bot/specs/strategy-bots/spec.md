## ADDED Requirements

### Requirement: Multi-Signal Consensus strategy

The system SHALL provide a **Multi-Signal Consensus** strategy, registered alongside the existing
strategies. It SHALL be a pure, long-only signal generator that, given recent bars, the current
position, and its parameters, returns one of ENTER_LONG or HOLD together with a human-readable
reason, performing no I/O and holding no persisted state. Its parameters SHALL be `window` (at
least 5, default 10), `consensus` (1 to 8, default 3), `rsi_period` (at least 2, default 14) and
`bb_k` (greater than 0, default 2).

Over the latest `window` closes, the latest included, with mean, population standard deviation σ
and median of those closes and c the latest close, eight signals SHALL each vote +1, −1 or 0:

- **z-score**: (c − mean) ÷ σ below −1 → +1, above 1 → −1 (0 when σ is 0);
- **SMA deviation**: (c − mean) ÷ mean below −1% → +1, above 1% → −1;
- **RSI** over the latest `rsi_period + 1` closes, from the simple means of gains and losses (100
  when the mean loss is 0): below 30 → +1, above 70 → −1;
- **Bollinger**: c below mean − `bb_k` × σ → +1, above mean + `bb_k` × σ → −1;
- **percentile rank** (the share of window closes strictly below c): below 10% → +1, above 90% →
  −1;
- **median**: (c − median) ÷ median below −0.2% → +1, above 0.2% → −1;
- **gradient**: c below the mean of the latest 5 closes → +1, above it → −1;
- **range**: c at or above the window high × 0.999 → −1, otherwise c at or below the window low ×
  1.001 → +1.

The score SHALL be the sum of the votes. While flat the strategy SHALL signal ENTER_LONG when the
score is at least `consensus`, and HOLD otherwise; its reason SHALL list the votes. While holding
it SHALL signal HOLD, leaving every exit to the engine's take-profit / stop-loss bracket and
drawdown kill-switch. With fewer than the larger of `window` and `rsi_period + 1` bars it SHALL
signal HOLD. It SHALL never signal a short entry.

#### Scenario: Enters on an oversold consensus

- **WHEN** the strategy is flat and the vote sum reaches `consensus`
- **THEN** the strategy SHALL signal ENTER_LONG

#### Scenario: Does not enter on a weak consensus

- **WHEN** the strategy is flat and the vote sum is below `consensus`
- **THEN** the strategy SHALL signal HOLD

#### Scenario: Overbought votes count against an entry

- **WHEN** some signals vote oversold and others overbought
- **THEN** the overbought votes SHALL be subtracted from the score

#### Scenario: RSI votes with its own history

- **WHEN** `rsi_period + 1` exceeds `window` and the RSI over the latest `rsi_period + 1` closes is
  below 30
- **THEN** the RSI signal SHALL vote +1

#### Scenario: Holds while in a position

- **WHEN** the strategy holds a position, whatever the score
- **THEN** the strategy SHALL signal HOLD and leave the exit to the engine

#### Scenario: Insufficient history

- **WHEN** fewer bars than the strategy needs are available
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
- **Volatility Regime Switcher (Algo 20)** — default for the Volatility Regime Switcher strategy:
  ATR window 20, SMA period 20, baseline 100 bars, reversion deviation 0; take-profit 0.5%,
  stop-loss 1%, drawdown limit 5% (the course script has no drawdown stop; 5% follows the catalog
  convention).
- **Multi-Signal Consensus (Algo 43)** — default for the Multi-Signal Consensus strategy: window
  10, consensus 3, RSI period 14, Bollinger multiplier 2; take-profit 0.5%, stop-loss 0.3%,
  drawdown limit 5% (the course's ₹5 / ₹3 bracket on a ~₹1,000 price; the course has no drawdown
  stop, 5% follows the catalog convention).

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

#### Scenario: Volatility Regime Switcher preset listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the Volatility Regime Switcher (Algo 20) preset as the Volatility Regime
  Switcher strategy's default

#### Scenario: Multi-Signal Consensus preset listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the Multi-Signal Consensus (Algo 43) preset as the Multi-Signal
  Consensus strategy's default
