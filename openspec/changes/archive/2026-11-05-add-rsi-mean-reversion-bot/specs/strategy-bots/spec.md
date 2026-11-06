## ADDED Requirements

### Requirement: RSI Mean Reversion strategy

The system SHALL provide an **RSI Mean Reversion** strategy, registered alongside
the existing strategies. It SHALL be a pure, long-only signal generator that, given
recent bars, the current position, and its parameters, returns one of ENTER_LONG,
EXIT, or HOLD together with a human-readable reason, performing no I/O and holding
no persisted state.

The strategy SHALL compute the Wilder-smoothed Relative Strength Index (RSI) of the
closing prices over a configurable `period`. Its behaviour SHALL be:

- when no position is open and the latest RSI is strictly below the `oversold`
  threshold, signal ENTER_LONG;
- when a long position is open and the latest RSI is strictly above the
  `exit_level` threshold, signal EXIT;
- otherwise signal HOLD.

The strategy SHALL be long-only: a high (overbought) RSI SHALL never open a short
position. Take-profit, stop-loss, and the drawdown kill-switch SHALL remain owned by
the engine and SHALL NOT be part of this strategy.

The strategy's parameters SHALL be `period` (a positive integer, default 14),
`oversold` (default 30) and `exit_level` (default 50), each a value on the RSI's
0–100 scale, with `oversold` strictly less than `exit_level`; invalid parameters
SHALL be rejected. The strategy SHALL require `period + 1` bars of history and, when
given fewer, SHALL signal HOLD rather than erroring. The strategy SHALL appear in
the strategy catalog with a display name and a human-readable explanation.

#### Scenario: Oversold RSI while flat enters long

- **WHEN** the RSI Mean Reversion strategy evaluates bars whose latest RSI is below
  the `oversold` threshold and no position is open
- **THEN** it SHALL return ENTER_LONG with a reason

#### Scenario: RSI reverting above the exit level exits

- **WHEN** the strategy evaluates bars whose latest RSI is above the `exit_level`
  threshold and a long position is open
- **THEN** it SHALL return EXIT with a reason

#### Scenario: RSI between thresholds holds

- **WHEN** the strategy evaluates bars whose latest RSI is at or above `oversold`
  (with no position) or at or below `exit_level` (while holding)
- **THEN** it SHALL return HOLD

#### Scenario: Overbought RSI never shorts

- **WHEN** the strategy evaluates bars whose latest RSI is high (overbought) and no
  position is open
- **THEN** it SHALL return HOLD rather than opening a short position

#### Scenario: Insufficient history holds

- **WHEN** the strategy is given fewer bars than its required history of `period + 1`
- **THEN** it SHALL return HOLD rather than erroring

#### Scenario: Invalid parameters are rejected

- **WHEN** a session is created with RSI parameters where `oversold` is not strictly
  less than `exit_level`, or a threshold is outside the 0–100 scale, or `period` is
  not a positive integer
- **THEN** the system SHALL reject the parameters with a validation error

#### Scenario: Catalog lists the RSI strategy

- **WHEN** a client requests the strategy catalog
- **THEN** the RSI Mean Reversion strategy SHALL be included with its display name,
  explanation, required history, and parameter schema
