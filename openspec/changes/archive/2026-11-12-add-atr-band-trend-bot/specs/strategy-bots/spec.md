## ADDED Requirements

### Requirement: ATR-Band Trend strategy

The system SHALL provide an **ATR-Band Trend** strategy, registered alongside the existing
strategies. It SHALL be a pure, long-only signal generator that, given recent bars, the current
position, and its parameters, returns one of ENTER_LONG, EXIT, or HOLD together with a
human-readable reason, performing no I/O and holding no persisted state. Its parameters SHALL be
a `version` (`supertrend` or `keltner`, default `supertrend`), a `window` (at least 2, default
20), an `atr_mult` (greater than 0, default 3) and `exit_on_midline` (default true, used by the
Keltner version). ATR SHALL be the mean absolute change between consecutive closes over the
window.

**SuperTrend version.** Over each rolling window of `window` closes, the strategy SHALL compute
the mid-range (highest + lowest close) / 2 and basic bands at mid-range ± `atr_mult` × ATR. While
the trend is up the upper band SHALL never rise above its previous value, and while the trend is
down the lower band SHALL never fall below its previous value. The first full window SHALL set
the trend up when its close is above the mid-range; afterwards the trend SHALL be up when the
close is above the previous SuperTrend line and down otherwise, and the SuperTrend line SHALL be
the lower band in an up-trend and the upper band in a down-trend. These values SHALL be computed
by replaying the bars provided, oldest first, so the result is deterministic for the same bars.
While flat, the strategy SHALL signal ENTER_LONG when the trend is up and the latest close is
above the SuperTrend line. While holding, it SHALL signal HOLD, leaving every exit to the
engine's take-profit / stop-loss bracket and drawdown kill-switch.

**Keltner version.** The strategy SHALL compute the simple moving average of the latest `window`
closes, including the current bar, and bands at that average ± `atr_mult` × ATR. While flat, it
SHALL signal ENTER_LONG when the latest close is strictly above the upper band. While holding,
it SHALL signal EXIT when `exit_on_midline` is on and the latest close is strictly below the
average, and HOLD otherwise.

With fewer bars than the strategy needs it SHALL signal HOLD. It SHALL never signal a short
entry.

#### Scenario: SuperTrend enters in an up-trend above the line

- **WHEN** the SuperTrend version is flat, the replayed trend is up and the latest close is
  above the SuperTrend line
- **THEN** the strategy SHALL signal ENTER_LONG

#### Scenario: SuperTrend does not enter in a down-trend

- **WHEN** the SuperTrend version is flat and the replayed trend is down
- **THEN** the strategy SHALL signal HOLD

#### Scenario: SuperTrend holds while in a position

- **WHEN** the SuperTrend version holds a position, even after the trend turns down
- **THEN** the strategy SHALL signal HOLD and leave the exit to the engine

#### Scenario: Keltner enters on an upper-band breakout

- **WHEN** the Keltner version is flat and the latest close is above SMA + `atr_mult` × ATR
- **THEN** the strategy SHALL signal ENTER_LONG

#### Scenario: Keltner exits below the midline

- **WHEN** the Keltner version holds a position, `exit_on_midline` is on and the latest close is
  below the SMA
- **THEN** the strategy SHALL signal EXIT

#### Scenario: Keltner without midline exit holds

- **WHEN** the Keltner version holds a position, `exit_on_midline` is off and the close is below
  the SMA
- **THEN** the strategy SHALL signal HOLD

#### Scenario: Insufficient history

- **WHEN** fewer bars than the strategy needs are available
- **THEN** the strategy SHALL signal HOLD

#### Scenario: Deterministic replay

- **WHEN** the strategy is evaluated twice on the same bars and position
- **THEN** it SHALL return the same signal both times

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

