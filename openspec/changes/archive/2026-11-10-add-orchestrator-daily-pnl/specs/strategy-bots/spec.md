## ADDED Requirements

### Requirement: Bot daily summary notification

When the daily bot snapshot job records an active session's snapshot, the system SHALL
send that session a **best-effort daily summary notification**, titled with the bot's
label, mirroring the AI portfolios' daily report: its value and day-over-day change (amount
and percentage, against the previous snapshot or, on the first day, its allocated capital;
the percentage omitted when that baseline is not positive), its total return (amount and
percentage), realised and unrealised P&L, cash, fees, Sharpe ratio, a benchmark comparison
when available, its best and worst open position when it has any, and the number of trades
it executed that day.

Sessions **deployed by a bot orchestrator** SHALL still be snapshotted but SHALL NOT send
their own daily summary notification; their orchestrator's daily notification covers them.
Manually created sessions SHALL keep their own notification.

The notification SHALL be a silent no-op when no notification channel is configured, and a
notification failure SHALL NOT fail the snapshot job.

#### Scenario: Daily summary notification sent per manual bot

- **WHEN** the daily snapshot job runs for an active, manually created bot session
- **THEN** the system SHALL send one notification for that session carrying its value and
  day change, total return, realised and unrealised P&L, cash, fees, Sharpe ratio, benchmark
  comparison when available, best and worst open position, and the day's trade count

#### Scenario: Orchestrator-deployed bots are snapshotted without their own push

- **WHEN** the daily snapshot job runs for an active session deployed by an orchestrator
- **THEN** the system SHALL record its daily snapshot and SHALL NOT send it a daily summary
  notification

#### Scenario: Summary notification is best-effort and silent when unconfigured

- **WHEN** the snapshot job runs while no notification channel is configured, or while a
  configured channel fails
- **THEN** the snapshots SHALL still be recorded and the job SHALL NOT fail because of the
  (absent or failed) notification
