## MODIFIED Requirements

### Requirement: Bot value snapshots and performance KPIs

The system SHALL record a daily value snapshot for each active bot session capturing
its total value — **cash plus the marked-to-market value of all open positions** — and
realised and unrealised profit/loss aggregated across the session's positions, and SHALL
expose per-session KPIs computed from the ledger and snapshots (for example current
value, **available (free, uninvested) cash**, total return, and realised/unrealised
profit/loss). These SHALL be computed within the strategy-bots subsystem and SHALL NOT
depend on the paper-trading subsystem's persistence.

#### Scenario: Daily snapshot recorded

- **WHEN** the daily snapshot job runs for an active bot session
- **THEN** the system SHALL persist a value snapshot with the session's total value
  (cash plus all marked positions) and aggregated realised/unrealised profit/loss for
  that date

#### Scenario: KPIs computed from the session's own data

- **WHEN** a client requests a bot session's KPIs
- **THEN** the system SHALL return figures computed from that session's own ledger
  and snapshots, aggregated across its positions

#### Scenario: KPIs include available cash

- **WHEN** a client requests a bot session's KPIs
- **THEN** the returned KPIs SHALL include the session's available (free, uninvested)
  cash balance — the cash not currently deployed in open positions

## ADDED Requirements

### Requirement: Session-list current value

When the system lists bot sessions, each listed session SHALL include its current value —
cash plus the marked-to-market value of its open positions — computed on the same basis as
the per-session current-value KPI. The current value SHALL be derived from the session's
latest recorded value snapshot when one exists, and SHALL fall back to cash plus open
positions valued at cost when the session has no snapshot yet.

#### Scenario: Listed session carries its current value

- **WHEN** a client lists bot sessions
- **THEN** each listed session SHALL include its current value, computed as cash plus the
  marked-to-market value of its open positions

#### Scenario: Current value before any snapshot exists

- **WHEN** a session that has not yet recorded a value snapshot is listed
- **THEN** its current value SHALL be reported as cash plus its open positions valued at
  cost
