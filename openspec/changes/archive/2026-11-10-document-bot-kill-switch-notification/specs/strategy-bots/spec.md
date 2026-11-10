## ADDED Requirements

### Requirement: Bot kill-switch notification

When the drawdown kill-switch stops a bot session during a tick, the system SHALL send one
**best-effort notification** titled with the bot's label, stating that the drawdown
kill-switch tripped, naming the positions it liquidated (their count and tickers, or that
there were no open positions to liquidate), the realised P&L booked on that liquidation, and
that the bot is now stopped. The notification SHALL be sent for every bot whose kill-switch
trips, including bots deployed by a bot orchestrator. It SHALL be a silent no-op when no
notification channel is configured, and a notification failure SHALL NOT prevent the
kill-switch from liquidating and stopping the bot or fail the tick. A tick in which no
kill-switch trips SHALL send no kill-switch notification.

#### Scenario: Kill-switch sends one notification

- **WHEN** a tick trips a bot's drawdown kill-switch while it holds two positions
- **THEN** the system SHALL send one notification titled with the bot's label that names
  both liquidated positions, the realised P&L of the liquidation, and that the bot is now
  stopped

#### Scenario: Kill-switch with no open positions

- **WHEN** a bot's kill-switch trips while it holds no open positions
- **THEN** the notification SHALL state that there were no open positions to liquidate

#### Scenario: No trip, no notification

- **WHEN** a tick processes a bot whose drawdown stays within its limit
- **THEN** no kill-switch notification SHALL be sent

#### Scenario: Notification failure does not block the stop

- **WHEN** the kill-switch trips while the notification channel is absent or fails
- **THEN** the bot SHALL still be liquidated and stopped, and the tick SHALL NOT fail
