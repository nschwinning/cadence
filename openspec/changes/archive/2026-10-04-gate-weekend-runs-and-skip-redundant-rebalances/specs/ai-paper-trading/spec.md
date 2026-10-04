## ADDED Requirements

### Requirement: Weekend crypto rebalance selects sessions by configured crypto scope

The scheduled crypto-only (weekend) rebalance SHALL select the sessions it rebalances by each session's **configured** asset scope rather than its current holdings. It SHALL rebalance only active daily-rebalancing AI-managed sessions whose configured asset scope includes crypto (scope is crypto or both). A session configured stocks-only SHALL be excluded from the crypto-only rebalance and reported as skipped for not being crypto-scoped, even if it currently holds or targets a crypto asset. A session with no persisted scope (for example one built before an explicit scope existed) SHALL be treated as the default scope (both) and is therefore included.

#### Scenario: Stocks-only session excluded even when holding crypto

- **WHEN** the crypto-only rebalance runs and an active daily-rebalancing session is configured stocks-only but currently holds or targets a crypto asset
- **THEN** the system SHALL exclude that session from the crypto-only rebalance, report it as skipped for not being crypto-scoped, and SHALL NOT place any crypto order for it

#### Scenario: Crypto and both scopes are rebalanced

- **WHEN** the crypto-only rebalance runs and an active daily-rebalancing session's configured scope is crypto or both
- **THEN** the system SHALL include that session in the crypto-only rebalance

### Requirement: Skip a rebalance run that can only buy with no deployable cash

During any rebalance (full or crypto-only), after the run has planned its sell and buy intents and **before it submits any order**, the system SHALL skip the run when the plan contains **no sell intents** AND the session has **no deployable unallocated cash** to fund the planned buys. Deployable unallocated cash SHALL be the session's free cash in excess of the reserved cash buffer — the cash available to fund new buys once the buffer is set aside — and is "none" when it is insufficient to fund any planned buy. When the run is skipped this way the system SHALL submit no orders, record the run as a skipped/no-op run, and send the informational skip notification described in "Notify when a selected session's rebalance is skipped" rather than the trade-success notification. A run whose plan includes at least one sell SHALL proceed (it reallocates), and a buy-only run that has deployable unallocated cash SHALL proceed (it deploys the cash). As a consequence, the first rebalance immediately after a build — when the allocated capital is already deployed and only the reserved cash buffer remains — SHALL be skipped.

#### Scenario: Buy-only plan with no deployable cash is skipped

- **WHEN** a rebalance plans only buy intents (no sells) and the session has no unallocated cash beyond the reserved cash buffer to fund them
- **THEN** the system SHALL submit no orders, record the run as skipped, and send the informational skip notification rather than a trade-success notification

#### Scenario: First rebalance right after a build is skipped

- **WHEN** the first rebalance after a build runs, with the allocated capital already deployed into positions and only the reserved cash buffer remaining
- **THEN** the planned run SHALL be buy-only with no deployable cash and the system SHALL skip it, submitting no orders and sending the informational skip notification

#### Scenario: Buy-only plan with deployable cash still runs

- **WHEN** a rebalance plans only buy intents (no sells) and the session holds unallocated cash beyond the reserved buffer
- **THEN** the system SHALL proceed with the run and deploy the cash into the planned buys

#### Scenario: Plan with a sell still runs

- **WHEN** a rebalance plans at least one sell intent
- **THEN** the system SHALL proceed with the run regardless of deployable cash

### Requirement: Notify when a selected session's rebalance is skipped

When a session's scheduled rebalance is actually engaged (the session was selected for the run) but the run is then skipped as a no-op, the system SHALL send one informational Pushover notification for that session naming the session's portfolio and the reason it was skipped, so the user is informed that the scheduled rebalance did nothing and why. This SHALL cover both the pre-agent crypto-only skip (no crypto to act on and no deployable cash to buy crypto) and the post-plan buy-only skip (no sells and no deployable cash, including the first rebalance after a build), on weekdays and weekends alike. This notification is informational and is distinct from the trade-success notification sent when a rebalance executes orders.

The system SHALL NOT send any notification for a session that was never engaged by the run — specifically a session excluded from the weekend crypto rebalance for not being crypto-scoped, and a stocks-only session skipped on a weekend end-of-day snapshot. Informing happens only when there was processing to report.

#### Scenario: Skipped crypto-only run informs the user

- **WHEN** a crypto-only rebalance for a selected session is skipped because it holds no crypto and has no deployable cash to buy crypto
- **THEN** the system SHALL send one informational notification naming the session's portfolio and the skip reason

#### Scenario: Skipped buy-only run informs the user

- **WHEN** a rebalance for a selected session is skipped because its plan is buy-only with no deployable cash (including the first rebalance after a build)
- **THEN** the system SHALL send one informational notification naming the session's portfolio and the skip reason

#### Scenario: Excluded and snapshot-skipped sessions stay silent

- **WHEN** a session is excluded from the weekend crypto rebalance for not being crypto-scoped, or a stocks-only session is skipped on a weekend end-of-day snapshot
- **THEN** the system SHALL send no notification for that session

## MODIFIED Requirements

### Requirement: Crypto-only rebalance scope

The system SHALL support a crypto-only rebalance that adjusts only a session's crypto
holdings and targets, leaving the session's equity positions untouched. When a
rebalance runs in crypto-only mode, the system SHALL restrict the candidate universe
and the holdings it acts on to crypto assets, regardless of the session's configured
asset scope, so that a session permitted to hold both equities and crypto still
rebalances only its crypto in this mode. The system SHALL NOT place any equity order
during a crypto-only rebalance, and SHALL NOT sell, trim, or add to equity positions.
Equity positions SHALL remain exactly as they were before the crypto-only run.

A crypto-only rebalance SHALL be recorded as skipped without invoking the agent when
the session has no crypto positions to act on and no deployable unallocated cash to buy
crypto (its free cash, net of the reserved cash buffer, is insufficient to fund a
crypto buy) — since it can then neither rotate existing crypto nor deploy cash into
crypto. This includes a crypto-scoped session (scope crypto or both) that currently
holds only equity shares and has no free capital. When the session holds crypto, or has
deployable cash to buy crypto, the run SHALL proceed.

#### Scenario: Mixed session rebalances only crypto

- **WHEN** a crypto-only rebalance runs for a session that holds both equities and
  crypto
- **THEN** the system SHALL place orders only for crypto assets and SHALL leave every
  equity position unchanged

#### Scenario: Candidates restricted to crypto

- **WHEN** the agent is invoked for a crypto-only rebalance
- **THEN** the candidate universe presented to the agent SHALL contain only crypto
  assets, even for a session whose asset scope permits equities

#### Scenario: No crypto means no agent run

- **WHEN** a crypto-only rebalance is requested for a session that neither holds nor
  targets any crypto
- **THEN** the system SHALL record the run as skipped and SHALL NOT invoke the agent

#### Scenario: Crypto-scoped session holding only shares with no free cash is skipped

- **WHEN** a crypto-only rebalance runs for a session whose configured scope includes
  crypto but which currently holds only equity shares and has no deployable unallocated
  cash to buy crypto
- **THEN** the system SHALL record the run as skipped without invoking the agent and
  SHALL place no orders, leaving the equity positions untouched

#### Scenario: Idle cash lets a crypto-scoped session deploy into crypto

- **WHEN** a crypto-only rebalance runs for a session whose configured scope includes
  crypto, holds no crypto yet, targets crypto, and has deployable unallocated cash
- **THEN** the system SHALL proceed with the run so the cash can be deployed into crypto

### Requirement: Snapshot session portfolio value at end of day

The system SHALL, on a scheduled end-of-day trigger, record one portfolio-value
snapshot per active AI-managed session **selected for the day** (a session whose
strategy is AI-managed and whose status is active) and send a daily
profit-and-loss report. On a **weekday** (Monday–Friday) the selected sessions SHALL
be all active AI-managed sessions. On a **weekend day** (Saturday or Sunday,
determined by calendar in the snapshot timezone, ignoring market holidays) the
selected sessions SHALL be only those whose **configured asset scope includes crypto**
(scope is crypto or both); an active AI-managed session configured stocks-only SHALL
be skipped entirely on a weekend — neither a snapshot recorded nor a notification
sent. A session with no persisted scope SHALL be treated as the default scope (both)
and is therefore included on weekends. The trigger SHALL be a cron-guarded endpoint
protected by the shared cron-token secret, and SHALL reject a request with a missing
or invalid token. Recording SHALL be idempotent per session per day: re-running the
trigger on the same calendar day SHALL update that day's snapshot rather than create a
duplicate.

The end-of-day snapshot and its P&L report are intended to run on **every calendar
day, including weekends**, so that a session's value and profit and loss are recorded
and reported on days its holdings move — notably its crypto sleeve, which trades
around the clock and is rebalanced on weekends. On weekends the trigger SHALL record
and report only for sessions whose configured scope includes crypto, since a
stocks-only session's holdings do not move while the equity market is closed. The
trigger SHALL operate on any day it is validly called, with no dependence on the equity
market being open; the scheduling cadence itself is a deployment concern (the cron
schedule), not enforced by this endpoint.

Each snapshot SHALL record the session's total value, its cash value, the market
value of its held positions, the day's profit and loss (absolute and percent), and a
per-position breakdown (per held ticker: quantity, price, market value, unrealized
profit and loss, and return). A session's total value SHALL be computed by marking its
open positions — taken from the session's position ledger — to market and combining
them with the session's allocated capital and realized profit and loss. The day's
profit and loss SHALL be measured against the
session's most recent prior snapshot, or against its allocated capital when no prior
snapshot exists. A session holding no positions SHALL record an all-cash snapshot.

The report SHALL contain, for each session snapshotted, a line with the session's
total value and the day's profit and loss (absolute and percent), the session's
benchmark and the session's return versus that benchmark (the benchmark's return over
the session's period and the session's excess return), plus the single
best-performing and single worst-performing individual holding ranked by return
across all snapshotted sessions. When a session's benchmark comparison is
unavailable, its line SHALL still be reported without the benchmark figures. A failure
to deliver the report SHALL NOT fail the snapshot job.

#### Scenario: Daily snapshot recorded for active AI sessions

- **WHEN** the end-of-day snapshot trigger runs on a weekday with a valid cron token
- **THEN** the system SHALL record a value snapshot for each active AI-managed
  session and SHALL NOT record snapshots for paused, stopped, or non-AI sessions

#### Scenario: Snapshot and report run on weekends

- **WHEN** the end-of-day snapshot trigger runs on a weekend (a day the equity
  market is closed) and a session's configured scope includes crypto
- **THEN** the system SHALL record a value snapshot for that session and send the
  daily P&L report, marking crypto and other holdings to market, without requiring the
  equity market to be open

#### Scenario: Weekend skips stocks-only sessions entirely

- **WHEN** the end-of-day snapshot trigger runs on a weekend and a session's
  configured scope does not include crypto (stocks only)
- **THEN** the system SHALL skip that session entirely — recording no snapshot and
  sending no notification for it

#### Scenario: Snapshot is idempotent per day

- **WHEN** the snapshot trigger runs twice on the same calendar day for a session
- **THEN** the system SHALL retain a single snapshot for that session and day,
  reflecting the latest run, rather than creating a duplicate

#### Scenario: Daily P&L baseline

- **WHEN** a snapshot is recorded for a session that has a prior snapshot
- **THEN** the day's profit and loss SHALL be the change in total value since the
  prior snapshot; **AND WHEN** the session has no prior snapshot, the day's profit
  and loss SHALL be measured against the session's allocated capital

#### Scenario: Daily report summarizes P&L and extremes

- **WHEN** the snapshot job completes with at least one session snapshotted
- **THEN** the system SHALL send a report with a per-session line showing value,
  P&L, and the session's return versus its benchmark, and with the best- and
  worst-performing individual holding across the snapshotted sessions

#### Scenario: Benchmark comparison unavailable in the report

- **WHEN** a snapshotted session's benchmark comparison cannot be computed
- **THEN** the session's report line SHALL still be included without the benchmark figures

#### Scenario: Report delivery failure does not fail the job

- **WHEN** report delivery fails
- **THEN** the snapshot job SHALL still complete and the recorded snapshots SHALL
  remain persisted

#### Scenario: Invalid cron token is rejected

- **WHEN** the snapshot trigger is called without a valid cron token
- **THEN** the system SHALL reject the request and record no snapshots
