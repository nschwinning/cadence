## MODIFIED Requirements

### Requirement: Live session performance KPIs

The system SHALL expose, on demand for a given paper-trading session, a summary of the session's live performance comprising: the current portfolio value (net asset value: cash plus open positions valued at current market quotes, net of cumulative transaction fees), the session's **unallocated (free) cash** (the current portfolio value less the market value of open positions), cumulative realised profit/loss, live unrealised profit/loss on open positions, cumulative transaction fees paid, the **daily average transaction cost** (defined below), total return relative to the allocated capital (as both an absolute money amount and a fraction), a risk-adjusted Sharpe ratio, the benchmark it is compared against, the benchmark's total return over the same period as a fraction, and the session's excess return over the benchmark as a fraction. The benchmark return SHALL be the fractional return of a buy-and-hold of the benchmark from the session's start to the latest available benchmark price, derived from the stored benchmark price series, and the excess return SHALL be the session's total-return fraction minus the benchmark's return fraction. When the benchmark has insufficient stored prices to compute a return the benchmark return and excess return SHALL be reported as unavailable (no value) rather than failing the request.

The **daily average transaction cost** SHALL be the session's cumulative transaction fees divided by the number of recorded daily value snapshots for the session. When the session has no recorded daily value snapshots the daily average transaction cost SHALL be reported as unavailable (no value) rather than dividing by zero.

Requesting the summary SHALL value the session's open positions against current quotes at request time (marking to market on load) rather than returning a stale stored valuation. A request for an unknown session SHALL fail as not found.

#### Scenario: Summary for a session with open positions

- **WHEN** a client requests the KPI summary for an existing session
- **THEN** the system SHALL mark the session's open positions to market and return the current portfolio value (net of transaction fees), the unallocated cash, realised P&L, unrealised P&L, cumulative transaction fees, the daily average transaction cost (or an unavailable value when the session has no snapshots), total return relative to allocated capital, the Sharpe ratio (or an unavailable Sharpe when history is insufficient), the benchmark return, and the excess return over the benchmark

#### Scenario: Unknown session

- **WHEN** a client requests the KPI summary for a session id that does not exist
- **THEN** the system SHALL respond with a not-found error and no summary

#### Scenario: Total return relative to allocated capital

- **WHEN** the KPI summary is computed
- **THEN** the total return SHALL be the current portfolio value measured against the session's allocated capital, provided both as an absolute money amount (current value minus allocated capital) and as a fraction of allocated capital

#### Scenario: Unallocated cash reported

- **WHEN** the KPI summary is computed for a session
- **THEN** the summary SHALL include the session's unallocated (free) cash as the current portfolio value less the market value of the session's open positions

#### Scenario: Benchmark and excess return reported

- **WHEN** the KPI summary is computed and the benchmark has sufficient stored prices
- **THEN** the summary SHALL include the benchmark's fractional return over the session's period and the session's excess return (the session's total-return fraction minus the benchmark's return fraction)

#### Scenario: Benchmark unavailable

- **WHEN** the KPI summary is computed but the benchmark has insufficient stored prices
- **THEN** the summary SHALL report the benchmark return and excess return as unavailable rather than failing the request

#### Scenario: Cumulative transaction fees reported

- **WHEN** a client requests the KPI summary for a session that has executed trades
- **THEN** the summary SHALL include the session's cumulative transaction fees as a non-negative money amount

#### Scenario: Daily average transaction cost reported

- **WHEN** the KPI summary is computed for a session that has at least one recorded daily value snapshot
- **THEN** the summary SHALL include the daily average transaction cost as the cumulative transaction fees divided by the number of recorded daily value snapshots

#### Scenario: Daily average transaction cost without snapshots

- **WHEN** the KPI summary is computed for a session that has no recorded daily value snapshots
- **THEN** the summary SHALL report the daily average transaction cost as unavailable rather than failing the request or dividing by zero
