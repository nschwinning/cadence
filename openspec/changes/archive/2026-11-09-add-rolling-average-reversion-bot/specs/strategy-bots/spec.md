## ADDED Requirements

### Requirement: Rolling-Average Reversion strategy

The system SHALL provide a **Rolling-Average Reversion** strategy, registered alongside
the existing strategies. It SHALL be a pure, long-only signal generator that, given
recent bars, the current position, and its parameters, returns one of ENTER_LONG, EXIT,
or HOLD together with a human-readable reason, performing no I/O and holding no
persisted state.

The strategy SHALL compute a rolling **average** over the latest `window` bars,
including the current bar, using the configured `average_type`:

- `sma` — the arithmetic mean of the closes;
- `typical` — the arithmetic mean of the typical prices, (high + low + close) / 3;
- `vwap` — the volume-weighted average of the closes, Σ(close × volume) / Σ(volume).

It SHALL measure the latest close's distance below that average using the configured
`distance` measure:

- `band` — the fractional deviation (close − average) / average. While flat, the
  strategy SHALL signal ENTER_LONG when the deviation is strictly below
  −`entry_threshold`; an `entry_threshold` of 0 therefore enters on any close strictly
  below the average (a bare cross).
- `zscore` — (close − average) divided by the population standard deviation of the
  window's price series (the closes, or the typical prices for `typical`). While flat,
  the strategy SHALL signal ENTER_LONG when the z-score is strictly below −`entry_z`.

While a long position is open, behaviour SHALL follow `exit_mode`:

- `revert` — signal EXIT once the close has reverted to or above the exit level: a
  deviation at or above −`exit_threshold` for `band`, or a z-score at or above −`exit_z`
  for `zscore`. A close that overshoots above the average SHALL therefore also exit.
- `bracket` — signal HOLD, deferring every exit to the engine's take-profit / stop-loss
  bracket and drawdown kill-switch.

Otherwise the strategy SHALL signal HOLD. When the measure is undefined for the window —
zero total volume for `vwap`, or zero standard deviation for `zscore` — it SHALL signal
HOLD rather than erroring. The strategy SHALL be long-only: a close above the average
SHALL never open a short position. Take-profit, stop-loss, and the drawdown kill-switch
SHALL remain owned by the engine.

The strategy's parameters SHALL be `average_type` (`sma`, `typical` or `vwap`, default
`sma`), `window` (an integer of at least 2, default 20), `distance` (`band` or `zscore`,
default `band`), `entry_threshold` and `exit_threshold` (fractions of at least 0 and below
1, defaults 0.01 and 0.005), `entry_z` and `exit_z` (at least 0, defaults 1.0 and 0.2),
and `exit_mode` (`revert` or `bracket`, default `revert`). In `revert` mode the exit level
SHALL lie strictly above the entry level — `exit_threshold` strictly less than
`entry_threshold` for `band`, `exit_z` strictly less than `entry_z` for `zscore` —
otherwise the parameters SHALL be rejected. The strategy SHALL require `window` bars of
history and, when given fewer, SHALL signal HOLD rather than erroring. The strategy SHALL
appear in the strategy catalog with a display name and a human-readable explanation.

#### Scenario: Band entry below the average while flat

- **WHEN** the strategy evaluates bars with `distance` band whose latest close is more than
  `entry_threshold` below the rolling average and no position is open
- **THEN** it SHALL return ENTER_LONG with a reason

#### Scenario: Close within the band holds while flat

- **WHEN** the strategy evaluates bars with `distance` band whose latest close is at or
  above the entry level and no position is open
- **THEN** it SHALL return HOLD

#### Scenario: Zero band enters on a bare cross below the average

- **WHEN** the strategy evaluates bars with `distance` band and `entry_threshold` 0 whose
  latest close is strictly below the rolling average and no position is open
- **THEN** it SHALL return ENTER_LONG

#### Scenario: Z-score entry while flat

- **WHEN** the strategy evaluates bars with `distance` zscore whose latest z-score is
  strictly below −`entry_z` and no position is open
- **THEN** it SHALL return ENTER_LONG with a reason

#### Scenario: Revert exit once price returns toward the average

- **WHEN** the strategy evaluates bars in `revert` mode while a long position is open and
  the latest close has reverted to or above the exit level (including above the average)
- **THEN** it SHALL return EXIT with a reason

#### Scenario: Revert mode holds while still below the exit level

- **WHEN** the strategy evaluates bars in `revert` mode while a long position is open and
  the latest close is still below the exit level
- **THEN** it SHALL return HOLD

#### Scenario: Bracket mode defers exits to the engine

- **WHEN** the strategy evaluates bars in `bracket` mode while a long position is open
- **THEN** it SHALL return HOLD regardless of where the close sits relative to the average

#### Scenario: Average types use their own price series

- **WHEN** the strategy evaluates the same bars with `average_type` sma, typical, and vwap
- **THEN** it SHALL compare the close against the mean of closes, the mean of typical
  prices, and the volume-weighted average of closes respectively

#### Scenario: Undefined measure holds

- **WHEN** the window has zero total volume with `average_type` vwap, or zero standard
  deviation with `distance` zscore
- **THEN** the strategy SHALL return HOLD rather than erroring

#### Scenario: Price above the average never shorts

- **WHEN** the strategy evaluates bars whose latest close is far above the rolling
  average and no position is open
- **THEN** it SHALL return HOLD and SHALL NOT open a short position

#### Scenario: Insufficient history holds

- **WHEN** the strategy is given fewer than `window` bars
- **THEN** it SHALL return HOLD rather than erroring

#### Scenario: Invalid parameters are rejected

- **WHEN** a session is created with an unknown `average_type`, `distance` or
  `exit_mode`, a `window` below 2, a negative threshold, or, in `revert` mode, an exit
  level not strictly above the entry level
- **THEN** the system SHALL reject the parameters with a validation error

#### Scenario: Catalog lists the Rolling-Average Reversion strategy

- **WHEN** a client requests the strategy catalog
- **THEN** the Rolling-Average Reversion strategy SHALL be included with its display
  name, explanation, required history, and parameter schema

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

### Requirement: Preset-driven build form

The bot build form SHALL load its presets from the preset catalog rather than from
values fixed in the client. The form SHALL open preconfigured with the default preset of
the initially selected strategy. Selecting a different strategy SHALL apply that strategy's
default preset to the strategy parameters and risk controls; for the Donchian range-breakout
strategy, selecting a version SHALL apply the preset for that version. When the selected
strategy has more than one preset, the form SHALL offer a **preset selector** listing that
strategy's presets; choosing one SHALL apply it, and the selector SHALL show the applied
preset. Every applied value SHALL remain editable. When the user changes any value that
came from the applied preset, the form SHALL indicate that the configuration is
customized. Submitting the form SHALL send the applied preset's key together with the
configured values.

#### Scenario: Form opens with the default preset

- **WHEN** a user opens the build form
- **THEN** the strategy parameters and risk controls SHALL be filled from the default
  preset of the initially selected strategy

#### Scenario: Switching strategy applies its default preset

- **WHEN** a user selects a different strategy in the build form
- **THEN** the form SHALL apply that strategy's default preset to the strategy
  parameters and risk controls

#### Scenario: Switching Donchian version applies the version's preset

- **WHEN** a user selects a Donchian version in the build form
- **THEN** the form SHALL apply the preset for that version

#### Scenario: Choosing a preset from the selector applies it

- **WHEN** the selected strategy has more than one preset and the user chooses one of them
  in the preset selector
- **THEN** the form SHALL apply that preset to the strategy parameters and risk controls
  and show it as the applied preset

#### Scenario: Editing a preset value marks the configuration customized

- **WHEN** a user changes a strategy parameter or risk control that the applied preset set
- **THEN** the form SHALL indicate that the configuration is customized, and the field
  SHALL keep the user's value
