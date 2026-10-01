# dashboard Specification

## Purpose
Gives the user a single at-a-glance summary of the state of their universe, portfolios, and paper-trading activity, so the health and scale of the system is visible without navigating into each area.

## Requirements

### Requirement: Aggregated dashboard metrics

The system SHALL provide a single endpoint returning aggregated metrics across the product: the size and composition of the asset universe (for example counts by category and by sector, and eligible vs. ineligible counts), the number of portfolios, and paper-trading activity (for example the number of active sessions and recent trades). The metrics SHALL be computed from current persisted data.

#### Scenario: Fetch dashboard metrics

- **WHEN** a client requests the dashboard metrics
- **THEN** the system SHALL return the current aggregated counts across assets, portfolios, and paper-trading sessions

#### Scenario: Empty system

- **WHEN** no assets, portfolios, or sessions exist yet
- **THEN** the system SHALL return zeroed metrics rather than an error

### Requirement: Range-scoped dashboard overview

The system SHALL provide a single endpoint returning an aggregated overview of the system scoped to a selected time range, where the range is one of `1D`, `1W`, `1M`, `YTD`, `1Y`, or `Max`. The overview SHALL aggregate over active paper-trading sessions only. It SHALL return, for the selected range, per-session performance data, an automation summary, a recent-activity list, a universe-balance summary, and universe performers. This overview SHALL be provided in addition to the existing aggregated dashboard metrics, which remain unchanged. When no active sessions or assets exist, the overview SHALL return empty collections and zeroed aggregates rather than an error.

#### Scenario: Fetch the overview for a range

- **WHEN** a client requests the dashboard overview for a given range
- **THEN** the system SHALL return the per-session performance data, automation summary, recent activity, universe balance, and universe performers computed for that range over the active sessions

#### Scenario: Unsupported range value

- **WHEN** a client requests the overview with a range outside the supported set
- **THEN** the system SHALL reject the request rather than silently defaulting

#### Scenario: Empty system

- **WHEN** there are no active sessions and no assets
- **THEN** the system SHALL return empty collections and zeroed aggregates rather than an error

### Requirement: Per-session performance data for the overview

For each active session the overview SHALL return the data needed to render aggregate performance and compare sessions over the selected range, without requiring the client to re-fetch when it changes which sessions are included. For each session this SHALL include a stable identifier, a display label, the allocated capital, the current value, the profit/loss and fees attributable to the selected range, and a value series over the range suitable for plotting. The value series SHALL be windowed to the selected range; a session that has no value before the range start SHALL be represented as contributing zero until its first recorded value.

#### Scenario: Session series windowed to the range

- **WHEN** the overview is requested for a range
- **THEN** each active session's returned value series SHALL cover the selected range and the session SHALL contribute zero for dates before its first recorded value

#### Scenario: Range-relative profit/loss and fees

- **WHEN** the overview is requested for a range
- **THEN** each session's returned profit/loss SHALL be its value at the end of the range minus its value at the start of the range, and its fees SHALL be those incurred within the range

### Requirement: Money-weighted aggregate performance

The overview SHALL define aggregate performance across a set of sessions as money-weighted rather than a simple average of per-session percentages. The aggregate return over a range SHALL be the sum of the sessions' range profit/loss divided by the sum of the sessions' value at the range start; for the maximum range it SHALL be measured against the sum of allocated capital. The aggregate profit/loss SHALL be the sum of the sessions' range profit/loss, and the aggregate value SHALL be the sum of the sessions' current values.

#### Scenario: Aggregate return is money-weighted

- **WHEN** aggregate performance is computed over multiple sessions of differing size
- **THEN** the aggregate return SHALL be the summed range profit/loss divided by the summed starting value (or summed allocated capital for the maximum range), not the mean of the sessions' individual return percentages

### Requirement: Automation summary in the overview

The overview SHALL include an automation summary describing the health of the AI run automation: the most recent rebalance run with its status and time, whether a run is currently in flight, the count of failed runs within the selected range, and the approximate next scheduled run derived from the fixed daily rebalance cron times. The next-run approximation SHALL be presented as approximate and MAY ignore market holidays.

#### Scenario: Automation health reported

- **WHEN** the overview is requested
- **THEN** it SHALL report the latest rebalance run's status and time, whether a run is in flight, the failed-run count within the range, and an approximate next run time

### Requirement: Recent activity in the overview

The overview SHALL include a list of recent AI runs across sessions within the selected range — covering build, rebalance, and close events — ordered newest first and limited to a capped number of entries. Each entry SHALL identify its session, its kind, its status, and its time.

#### Scenario: Recent activity within the range

- **WHEN** the overview is requested for a range
- **THEN** it SHALL return the most recent AI runs within that range, newest first, capped at a maximum count, each identifying its session, kind, status, and time

### Requirement: Universe balance and performers in the overview

The overview SHALL include a universe-balance summary and universe performers. The balance summary SHALL describe the current composition of the asset universe independent of the selected range: the eligible versus ineligible split, the number of sectors represented, the largest sector's share, and the largest category's share. The performers SHALL list the best and worst tracked assets by market return over the selected range, each limited to a small fixed count, using per-asset market returns derived from stored price history; assets without enough history to produce a return for the range SHALL be excluded from the ranking.

#### Scenario: Balance summary is range-independent

- **WHEN** the overview is requested for any range
- **THEN** the universe-balance summary SHALL reflect the current composition (eligible/ineligible split, sectors represented, largest sector and category shares) regardless of the selected range

#### Scenario: Best and worst performers over the range

- **WHEN** the overview is requested for a range
- **THEN** it SHALL return the best and worst tracked assets by market return over that range, each capped at a small fixed count, excluding assets that lack enough stored history to produce a return for the range
