## ADDED Requirements

### Requirement: Orchestrator daily snapshots

The evening bot snapshot job SHALL, after recording the bots' daily snapshots, record one
daily snapshot per **active** orchestrator for that date, capturing its value, free
capital, allocated capital and number of active bots (as defined by the capital-pool
requirement). There SHALL be at most one snapshot per orchestrator per date; running the
job again on the same date SHALL update that date's snapshot rather than add another.
Stopped and archived orchestrators SHALL NOT be snapshotted. Before snapshotting, the job
SHALL settle any capital that finished bots return to the pool, so the figures are
current.

#### Scenario: Active orchestrator is snapshotted daily

- **WHEN** the evening snapshot job runs with one active orchestrator
- **THEN** the system SHALL record a snapshot for that date with its value, free capital,
  allocated capital and active bots

#### Scenario: Rerun on the same day updates the snapshot

- **WHEN** the job runs twice on the same date
- **THEN** the orchestrator SHALL have a single snapshot for that date carrying the latest
  figures

#### Scenario: Stopped orchestrators are not snapshotted

- **WHEN** the job runs while an orchestrator is stopped or archived
- **THEN** no snapshot SHALL be recorded for it

## MODIFIED Requirements

### Requirement: Orchestrator notifications

Scheduled runs SHALL send a push notification when notifications are configured: on
success or partial success, a summary naming the orchestrator and the bots stopped and
deployed; on failure, the orchestrator and the error. Skipped runs and manual runs SHALL NOT
notify. A notification failure SHALL NOT fail the run.

In addition, the evening snapshot job SHALL send **one daily P&L notification per active
orchestrator** after recording its snapshot, titled with the orchestrator's label, carrying:

- its value and **day change** as an amount and a percentage, against the previous
  snapshot's value or, when there is no earlier snapshot, against the capital pool (the
  percentage is omitted when that baseline is not positive);
- its **total return** on the capital pool as an amount and a percentage;
- its free capital, allocated capital, and active bots out of the maximum;
- a **benchmark comparison** — the orchestrator's benchmark return and the excess return
  since its first snapshot — when the benchmark has usable stored closes, omitted otherwise;
- its **best and worst bot** by that day's P&L among its active bots, omitted when it has
  no active bot;
- the bots it **started** that day, each with its preset, tickers and capital, or that
  none were started;
- the bots **stopped** that day — whether by an orchestrator decision or by the bot's own
  drawdown kill-switch — each with its preset, tickers, stop reason and return on its
  allocated capital, or that none were stopped;
- the status of that day's **decision run**, or that no decision run happened that day.

Each of the started and stopped lists SHALL show at most five bots, summarising any
further bots as a count, so the notification stays within the channel's message limit.

This daily notification SHALL replace the individual daily notifications of the bots the
orchestrator deployed. It SHALL be best-effort: a silent no-op when no notification channel
is configured, and a notification failure SHALL NOT fail the snapshot job.

#### Scenario: Scheduled run notifies a summary

- **WHEN** a scheduled run deploys one bot and stops one bot
- **THEN** a notification SHALL name the orchestrator and both bots

#### Scenario: Manual run is silent

- **WHEN** a manual run completes
- **THEN** no notification SHALL be sent

#### Scenario: Daily P&L notification per active orchestrator

- **WHEN** the evening snapshot job runs for an active orchestrator with two active bots
  and a previous snapshot
- **THEN** one notification SHALL be sent for it with its value, day change against the
  previous snapshot, total return, free and allocated capital, active bots out of the
  maximum, its best and worst bot, the bots started and stopped that day, and that day's
  decision-run status

#### Scenario: First day compares against the capital pool

- **WHEN** an orchestrator's first snapshot is recorded
- **THEN** its day change SHALL be measured against its capital pool

#### Scenario: Daily notification names bots started and stopped today

- **WHEN** an orchestrator deployed one bot that morning and stopped another, and a third of
  its bots was stopped by its drawdown kill-switch during the day
- **THEN** the daily notification SHALL list the started bot with its preset, tickers and
  capital, and both stopped bots with their preset, tickers, stop reason (orchestrator or
  kill-switch) and return

#### Scenario: Long lists are capped

- **WHEN** more than five bots were started (or stopped) that day
- **THEN** the notification SHALL list five of them and summarise the rest as a count

#### Scenario: No decision run today

- **WHEN** no decision run happened for the orchestrator that day (for example on a
  weekly cadence)
- **THEN** the daily notification SHALL say that no decision run happened today

#### Scenario: Daily notification is best-effort

- **WHEN** the snapshot job runs while no notification channel is configured, or the
  channel fails
- **THEN** the snapshots SHALL still be recorded and the job SHALL NOT fail
