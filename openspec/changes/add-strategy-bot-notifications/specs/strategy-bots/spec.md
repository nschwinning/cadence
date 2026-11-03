## MODIFIED Requirements

### Requirement: Optional take-profit, stop-loss, and drawdown kill-switch

A bot session MAY configure an optional take-profit and an optional stop-loss as
percentage thresholds against each open position's entry price; when unset, neither
triggers. On each tick, for **every open position** the system SHALL exit that position
if its current price has risen to or above the take-profit threshold or fallen to or
below the stop-loss threshold, independently of the strategy signal. The system SHALL
also enforce a **whole-session** drawdown kill-switch: when a session's total value
falls by at least the configured drawdown limit from its peak, the system SHALL exit
**all** open positions and stop the session so it is no longer ticked. When the
kill-switch stops a session, the system SHALL send a **best-effort notification**
identifying the bot, the positions it liquidated, the realised profit/loss on the
liquidation, and that the bot is now stopped. The notification SHALL be a silent no-op
when no notification channel is configured, and a notification failure SHALL NOT fail
the tick or prevent the session from being stopped.

#### Scenario: Take-profit exits

- **WHEN** an open position with a configured take-profit ticks at a price at or above
  the take-profit threshold
- **THEN** the system SHALL exit that position regardless of the strategy signal

#### Scenario: Stop-loss exits

- **WHEN** an open position with a configured stop-loss ticks at a price at or below the
  stop-loss threshold
- **THEN** the system SHALL exit that position regardless of the strategy signal

#### Scenario: Thresholds unset never trigger

- **WHEN** a session has no take-profit and no stop-loss configured
- **THEN** neither a take-profit nor a stop-loss exit SHALL occur for any position

#### Scenario: Drawdown kill-switch stops the session

- **WHEN** a session's total value has fallen by at least the drawdown limit from its
  peak
- **THEN** the system SHALL exit all open positions and stop the session

#### Scenario: Drawdown kill-switch sends a notification

- **WHEN** a tick trips a session's drawdown kill-switch, liquidating its open positions
  and stopping it
- **THEN** the system SHALL send one notification naming the bot, the liquidated
  positions, the realised profit/loss on the liquidation, and that the bot is now
  stopped

#### Scenario: Notification is best-effort and silent when unconfigured

- **WHEN** the kill-switch trips while no notification channel is configured, or while a
  configured channel fails to deliver
- **THEN** the session SHALL still be liquidated and stopped, and the tick SHALL NOT
  fail because of the (absent or failed) notification

### Requirement: Bot value snapshots and performance KPIs

The system SHALL record a daily value snapshot for each active bot session capturing
its total value — **cash plus the marked-to-market value of all open positions** — and
realised and unrealised profit/loss aggregated across the session's positions, and SHALL
expose per-session KPIs computed from the ledger and snapshots (for example current
value, total return, realised/unrealised profit/loss, and a **risk-adjusted return
(Sharpe ratio)**). The Sharpe ratio SHALL be computed from the session's own daily
value-snapshot series on the same basis the paper-trading subsystem uses, and SHALL be
reported as unavailable (null) until the session has accumulated enough daily
observations. These SHALL be computed within the strategy-bots subsystem and SHALL NOT
depend on the paper-trading subsystem's persistence. When the daily snapshot job records
a session's snapshot, it SHALL send a
**best-effort per-bot daily summary notification** mirroring the figures the AI
paper-trading daily report provides — the session's value and its day-over-day change in
amount and percent, total return in amount and percent, realised and unrealised
profit/loss, cash, fees, a risk-adjusted return (Sharpe) figure, a benchmark comparison,
and the session's best and worst open position — **plus the number of trades the session
executed that day**. The daily trade count SHALL reflect only trades executed on the
snapshot date, distinct from the session's lifetime trade count. The summary
notification SHALL be a silent no-op when no notification channel is configured, and a
notification failure SHALL NOT fail the snapshot job.

#### Scenario: Daily snapshot recorded

- **WHEN** the daily snapshot job runs for an active bot session
- **THEN** the system SHALL persist a value snapshot with the session's total value
  (cash plus all marked positions) and aggregated realised/unrealised profit/loss for
  that date

#### Scenario: KPIs computed from the session's own data

- **WHEN** a client requests a bot session's KPIs
- **THEN** the system SHALL return figures computed from that session's own ledger
  and snapshots, aggregated across its positions

#### Scenario: KPIs include a Sharpe ratio when enough history exists

- **WHEN** a client requests a bot session's KPIs
- **THEN** the system SHALL include a risk-adjusted return (Sharpe ratio) computed from
  the session's own daily value-snapshot series, reported as unavailable (null) until the
  session has accumulated enough daily observations

#### Scenario: Daily summary notification sent per bot

- **WHEN** the daily snapshot job records a snapshot for an active bot session
- **THEN** the system SHALL send one notification for that session carrying its value and
  day-over-day change, total return, realised/unrealised profit/loss, cash, fees, a
  Sharpe figure, a benchmark comparison, its best and worst open position, and the number
  of trades it executed that day

#### Scenario: Daily trade count reflects only the day's trades

- **WHEN** the daily summary is built for a session that executed some trades on the
  snapshot date and others on earlier dates
- **THEN** the reported trade count SHALL include only the trades executed on the
  snapshot date, not the session's lifetime total

#### Scenario: Summary notification is best-effort and silent when unconfigured

- **WHEN** the snapshot job runs while no notification channel is configured, or while a
  configured channel fails to deliver
- **THEN** the system SHALL still record the value snapshots, and the snapshot job SHALL
  NOT fail because of the (absent or failed) notification
