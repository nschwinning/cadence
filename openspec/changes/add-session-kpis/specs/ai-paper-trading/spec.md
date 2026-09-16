## ADDED Requirements

### Requirement: Live session performance KPIs

The system SHALL expose, on demand for a given paper-trading session, a summary of the session's live performance comprising: the current portfolio value (net asset value: cash plus open positions valued at current market quotes), cumulative realised profit/loss, live unrealised profit/loss on open positions, total return relative to the allocated capital (as both an absolute money amount and a fraction), and a risk-adjusted Sharpe ratio. Requesting the summary SHALL value the session's open positions against current quotes at request time (marking to market on load) rather than returning a stale stored valuation. A request for an unknown session SHALL fail as not found.

#### Scenario: Summary for a session with open positions

- **WHEN** a client requests the KPI summary for an existing session
- **THEN** the system SHALL mark the session's open positions to market and return the current portfolio value, realised P&L, unrealised P&L, total return relative to allocated capital, and the Sharpe ratio (or an unavailable Sharpe when history is insufficient)

#### Scenario: Unknown session

- **WHEN** a client requests the KPI summary for a session id that does not exist
- **THEN** the system SHALL respond with a not-found error and no summary

#### Scenario: Total return relative to allocated capital

- **WHEN** the KPI summary is computed
- **THEN** the total return SHALL be the current portfolio value measured against the session's allocated capital, provided both as an absolute money amount (current value minus allocated capital) and as a fraction of allocated capital

### Requirement: Sharpe ratio from the session's daily NAV series

The system SHALL compute a session's Sharpe ratio from the session's own ordered series of daily net-asset-value returns (the recorded daily value snapshots), as the mean daily return in excess of a configurable risk-free rate (defaulting to zero) divided by the standard deviation of daily returns, annualised by the square root of a configurable number of trading days per year. The Sharpe ratio SHALL be reported as unavailable (no value) when the session has fewer than a configured minimum number of daily returns, or when the daily returns have zero standard deviation. The computation SHALL rely solely on the session's recorded daily NAV series and SHALL NOT fetch external price history.

#### Scenario: Sufficient history

- **WHEN** a session has at least the configured minimum number of daily returns with non-zero variation
- **THEN** the system SHALL report a Sharpe ratio equal to the annualised mean-over-standard-deviation of those daily returns

#### Scenario: Insufficient history

- **WHEN** a session has fewer than the configured minimum number of daily returns
- **THEN** the system SHALL report the Sharpe ratio as unavailable rather than a computed value

#### Scenario: No volatility

- **WHEN** a session's daily returns have zero standard deviation
- **THEN** the system SHALL report the Sharpe ratio as unavailable rather than dividing by zero
