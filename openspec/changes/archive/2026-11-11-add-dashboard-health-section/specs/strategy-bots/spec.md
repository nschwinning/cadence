## ADDED Requirements

### Requirement: Tick outcome log

Every bot tick SHALL record its outcome: when it ran, whether the equity market was open, how
many bots were processed, skipped and failed, how many previously unrecorded orders were
reconciled, and — when the tick itself failed before completing — that it failed, with a
non-secret error message. A tick that finds the market closed SHALL still be recorded.
Recording the outcome SHALL NOT itself fail the tick, and an outcome SHALL be recorded even
when the tick fails. Outcomes older than 7 days SHALL be deleted by the daily bot snapshot job.

#### Scenario: Tick with a failing bot is recorded

- **WHEN** a tick processes one bot successfully and another bot fails
- **THEN** a tick outcome SHALL be recorded with one processed and one failed bot

#### Scenario: Market-closed tick is recorded

- **WHEN** a tick runs while the equity market is closed
- **THEN** a tick outcome SHALL be recorded marked as market closed

#### Scenario: Crashed tick is recorded

- **WHEN** a tick fails before completing
- **THEN** a tick outcome SHALL be recorded as failed with its error message

#### Scenario: Old outcomes are pruned

- **WHEN** the daily bot snapshot job runs
- **THEN** tick outcomes older than 7 days SHALL be deleted and newer ones kept

### Requirement: Per-bot failure state

When processing a bot during a tick fails, the system SHALL record on that bot when the failure
happened, a non-secret error message (for example the broker's rejection reason), and the number
of consecutive ticks in which it has failed. The next tick in which the bot is processed without
failing SHALL clear the failure state. A bot skipped for lack of fresh market data SHALL neither
set nor clear it. The failure state SHALL be part of the bot's read model.

#### Scenario: Failure is recorded and counted

- **WHEN** a bot fails in two consecutive ticks with a broker rejection
- **THEN** the bot SHALL report two consecutive failures, the time of the latest one and the
  rejection message

#### Scenario: Success clears the failure

- **WHEN** a failing bot is processed successfully in a later tick
- **THEN** its failure state SHALL be cleared

### Requirement: Bot failure banner

The bot detail view SHALL show a red banner while the bot has a recorded failure, stating how
many consecutive ticks have failed, when the latest failure happened and its error message. No
banner SHALL be shown for a bot without a recorded failure.

#### Scenario: Failing bot shows the banner

- **WHEN** the operator opens a bot that failed in its last three ticks
- **THEN** the page SHALL show a red banner with three consecutive failures, the latest failure
  time and the error

#### Scenario: Healthy bot shows no banner

- **WHEN** the operator opens a bot without a recorded failure
- **THEN** no failure banner SHALL be shown
