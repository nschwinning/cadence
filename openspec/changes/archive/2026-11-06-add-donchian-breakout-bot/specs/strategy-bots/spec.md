## ADDED Requirements

### Requirement: Donchian Range Breakout strategy

The system SHALL provide a **Donchian Range Breakout** strategy, registered
alongside the existing strategies. It SHALL be a pure, long-only signal generator
that, given recent bars, the current position, and its parameters, returns one of
ENTER_LONG, EXIT, or HOLD together with a human-readable reason, performing no I/O
and holding no persisted state.

The strategy SHALL expose a `version` parameter selecting one of two variants of
the same Donchian-channel-breakout indicator, computed over a window of bars that
**precede** the current bar (the current bar is excluded so a close can break out
of the channel):

- **Turtle rolling channel.** Behaviour:
  - when no position is open and the latest close is strictly above the highest
    high of the previous `entry_period` bars, signal ENTER_LONG;
  - when a long position is open and the latest close is strictly below the lowest
    low of the previous `exit_period` bars, signal EXIT;
  - otherwise signal HOLD.
- **Locked channel.** Behaviour:
  - when no position is open, compute the upper band as the highest high of the
    previous `channel_period` bars plus `atr_padding_mult × ATR` (where ATR is a
    simple average of the absolute successive close differences over the channel
    window; a padding multiplier of `0` yields the raw channel and a positive
    multiplier yields a false-breakout buffer), and signal ENTER_LONG when the
    latest close is strictly above that upper band;
  - when a long position is open, signal HOLD — the strategy emits no channel exit;
    exits are deferred entirely to the engine's take-profit / stop-loss bracket and
    drawdown kill-switch.

The strategy SHALL be long-only: a downward breakout SHALL never open a short
position. Take-profit, stop-loss, the drawdown kill-switch, and position sizing
SHALL remain owned by the engine and SHALL NOT be part of this strategy.

The strategy's parameters SHALL be `version` (`turtle` or `locked`, default
`turtle`), `entry_period` (a positive integer, default 20), `exit_period` (a
positive integer, default 10, strictly less than `entry_period`), `channel_period`
(a positive integer, default 20) and `atr_padding_mult` (a non-negative number,
default 0.5); invalid parameters SHALL be rejected. The strategy SHALL require
`entry_period + 1` bars of history in the Turtle version and `channel_period + 1`
bars in the Locked version and, when given fewer, SHALL signal HOLD rather than
erroring. The strategy SHALL appear in the strategy catalog with a display name and
a human-readable explanation describing both versions.

#### Scenario: Turtle upper breakout while flat enters long

- **WHEN** the Turtle version evaluates bars whose latest close is strictly above
  the highest high of the previous `entry_period` bars and no position is open
- **THEN** it SHALL return ENTER_LONG with a reason

#### Scenario: Turtle lower breakdown while holding exits

- **WHEN** the Turtle version evaluates bars whose latest close is strictly below
  the lowest low of the previous `exit_period` bars and a long position is open
- **THEN** it SHALL return EXIT with a reason

#### Scenario: Turtle price inside the channel holds

- **WHEN** the Turtle version evaluates bars whose latest close is at or below the
  entry high (with no position) or at or above the exit low (while holding)
- **THEN** it SHALL return HOLD

#### Scenario: Locked padded breakout while flat enters long

- **WHEN** the Locked version evaluates bars whose latest close is strictly above
  the highest high of the previous `channel_period` bars padded by
  `atr_padding_mult × ATR`, and no position is open
- **THEN** it SHALL return ENTER_LONG with a reason

#### Scenario: Locked while holding defers the exit to the engine

- **WHEN** the Locked version evaluates bars while a long position is open
- **THEN** it SHALL return HOLD, leaving the exit to the engine's take-profit /
  stop-loss bracket and drawdown kill-switch

#### Scenario: Downward breakout never shorts

- **WHEN** the strategy evaluates a downward breakout while no position is open
- **THEN** it SHALL return HOLD rather than opening a short position

#### Scenario: Insufficient history holds

- **WHEN** the strategy is given fewer bars than its required history (`entry_period
  + 1` for Turtle, `channel_period + 1` for Locked)
- **THEN** it SHALL return HOLD rather than erroring

#### Scenario: Invalid parameters are rejected

- **WHEN** a session is created with Donchian parameters where `exit_period` is not
  strictly less than `entry_period`, a period is not a positive integer,
  `atr_padding_mult` is negative, or `version` is not one of the allowed values
- **THEN** the system SHALL reject the parameters with a validation error

#### Scenario: Catalog lists the Donchian strategy with both versions

- **WHEN** a client requests the strategy catalog
- **THEN** the Donchian Range Breakout strategy SHALL be included with its display
  name, explanation describing both the Turtle and Locked versions, required
  history, and parameter schema
