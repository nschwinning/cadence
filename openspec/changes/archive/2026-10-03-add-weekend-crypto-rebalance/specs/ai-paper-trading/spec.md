## ADDED Requirements

### Requirement: Crypto-only rebalance scope

The system SHALL support a crypto-only rebalance that adjusts only a session's crypto
holdings and targets, leaving the session's equity positions untouched. When a
rebalance runs in crypto-only mode, the system SHALL restrict the candidate universe
and the holdings it acts on to crypto assets, regardless of the session's configured
asset scope, so that a session permitted to hold both equities and crypto still
rebalances only its crypto in this mode. The system SHALL NOT place any equity order
during a crypto-only rebalance, and SHALL NOT sell, trim, or add to equity positions.
Equity positions SHALL remain exactly as they were before the crypto-only run.

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

### Requirement: Crypto-only rebalance sizes against the crypto investable budget

In a crypto-only rebalance the system SHALL size crypto target weights against the
session's **crypto investable budget**, defined as the current market value of the
session's crypto positions plus the session's unallocated (free) cash — not against
the session's full allocated capital. The unallocated cash SHALL be the session's
derived free cash (allocated capital adjusted by realised profit/loss and fees, plus
unrealised position value, less the market value of all open positions). Sizing
against this budget SHALL allow the run both to rotate capital between existing crypto
positions and to deploy idle cash into crypto, while never drawing on capital tied up
in equity positions. The crypto-only run SHALL NOT size any position against the full
allocated capital.

#### Scenario: Weights applied to the crypto budget, not total capital

- **WHEN** a crypto-only rebalance sizes a crypto target for a session that also holds
  equities
- **THEN** the system SHALL compute the target position value from the crypto
  investable budget (crypto positions' market value plus unallocated cash), not from
  the session's full allocated capital

#### Scenario: Idle cash can be deployed into crypto

- **WHEN** a crypto-only rebalance runs for a session that holds unallocated cash and
  targets a larger crypto allocation
- **THEN** the system SHALL be able to buy crypto up to the crypto investable budget,
  including the unallocated cash

#### Scenario: Equity capital is never used for crypto

- **WHEN** a crypto-only rebalance sizes crypto positions
- **THEN** the capital tied up in the session's equity positions SHALL NOT be included
  in the crypto investable budget

### Requirement: Rebalance agent informed of the session's unallocated cash

The system SHALL provide the rebalance agent with the session's own derived
unallocated (free) cash in the account summary it receives, rather than a global or
broker-wide cash figure that does not reflect the individual session's capital. For a
crypto-only rebalance the account summary SHALL additionally convey the crypto
investable budget the agent's crypto weights will be sized against. The cash figure
presented to the agent SHALL be the session-derived unallocated cash described in
"Crypto-only rebalance sizes against the crypto investable budget".

#### Scenario: Account summary carries session cash

- **WHEN** the rebalance agent is invoked for a session
- **THEN** the account summary SHALL report the session's own derived unallocated
  cash rather than a shared broker-wide buying-power figure

#### Scenario: Crypto budget conveyed for crypto-only runs

- **WHEN** the rebalance agent is invoked for a crypto-only rebalance
- **THEN** the account summary SHALL additionally convey the crypto investable budget
  (crypto positions' market value plus unallocated cash)

### Requirement: Crypto-only rebalance uses a crypto-scoped prompt

A crypto-only rebalance SHALL use a rebalance prompt whose instructions make clear
that the agent is rebalancing only the session's crypto sleeve within the provided
crypto investable budget, and that equities will not be traded in this run. This
crypto-scoped prompt SHALL be stored as a versioned rebalance-prompt record under the
same versioning rules as the standard rebalance prompt (see "Versioned rebalancing
prompt stored in the database"); it SHALL NOT be a prompt hardcoded in application
code. A crypto-only run SHALL fail with a clear error, rather than invoking the agent
with an empty prompt, if its crypto-scoped prompt cannot be found.

#### Scenario: Crypto-only run uses the crypto-scoped prompt

- **WHEN** a crypto-only rebalance invokes the agent
- **THEN** the system SHALL use the crypto-scoped rebalance prompt, instructing the
  agent that only the crypto sleeve is being rebalanced within the crypto investable
  budget

#### Scenario: Missing crypto prompt fails cleanly

- **WHEN** a crypto-only rebalance runs and its crypto-scoped prompt cannot be found
- **THEN** the system SHALL fail the rebalance with an explicit error and SHALL NOT
  invoke the agent with an empty prompt

## MODIFIED Requirements

### Requirement: Live session performance KPIs

The system SHALL expose, on demand for a given paper-trading session, a summary of the session's live performance comprising: the current portfolio value (net asset value: cash plus open positions valued at current market quotes, net of cumulative transaction fees), the session's **unallocated (free) cash** (the current portfolio value less the market value of open positions), cumulative realised profit/loss, live unrealised profit/loss on open positions, cumulative transaction fees paid, total return relative to the allocated capital (as both an absolute money amount and a fraction), a risk-adjusted Sharpe ratio, the benchmark it is compared against, the benchmark's total return over the same period as a fraction, and the session's excess return over the benchmark as a fraction. The benchmark return SHALL be the fractional return of a buy-and-hold of the benchmark from the session's start to the latest available benchmark price, derived from the stored benchmark price series, and the excess return SHALL be the session's total-return fraction minus the benchmark's return fraction. When the benchmark has insufficient stored prices to compute a return the benchmark return and excess return SHALL be reported as unavailable (no value) rather than failing the request. Requesting the summary SHALL value the session's open positions against current quotes at request time (marking to market on load) rather than returning a stale stored valuation. A request for an unknown session SHALL fail as not found.

#### Scenario: Summary for a session with open positions

- **WHEN** a client requests the KPI summary for an existing session
- **THEN** the system SHALL mark the session's open positions to market and return the current portfolio value (net of transaction fees), the unallocated cash, realised P&L, unrealised P&L, cumulative transaction fees, total return relative to allocated capital, the Sharpe ratio (or an unavailable Sharpe when history is insufficient), the benchmark return, and the excess return over the benchmark

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
