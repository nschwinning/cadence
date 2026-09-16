## ADDED Requirements

### Requirement: Per-trade transaction cost

The system SHALL charge a fixed transaction cost on every executed trade it
records for a paper-trading session, regardless of side (buy or sell). The cost
per trade SHALL be a single configurable amount (defaulting to one US dollar) and
SHALL be applied at the single point where a trade is recorded, so that no trade
can be recorded without incurring the cost. The system SHALL accumulate these
costs per session as a cumulative, non-negative transaction-fees total.

A session's current portfolio value SHALL be net of its cumulative transaction
fees: the value SHALL equal the allocated capital plus cumulative realised
profit/loss, minus cumulative transaction fees, plus live unrealised profit/loss
on open positions. Consequently the cash portion of the valuation and the daily
value snapshots SHALL reflect fees paid. The realised profit/loss recorded on an
individual closed position SHALL remain gross (derived from entry and exit prices
only) — transaction fees SHALL be tracked at the session level rather than folded
into per-position realised profit/loss.

The transaction cost SHALL apply going forward only: sessions that predate this
capability SHALL begin with a cumulative fees total of zero and SHALL NOT have
historical trades re-priced. New trades on any session, old or new, SHALL incur
the cost from this point on.

#### Scenario: Recording a trade charges the cost

- **WHEN** the system records an executed trade for a session
- **THEN** the session's cumulative transaction fees SHALL increase by the
  configured per-trade cost
- **AND** a session that executes two trades in a run SHALL accrue twice the
  per-trade cost

#### Scenario: Portfolio value is net of fees

- **WHEN** the system values a session that has accrued transaction fees
- **THEN** the reported current portfolio value SHALL subtract the session's
  cumulative transaction fees from what it would otherwise be

#### Scenario: Closed-position realised P&L stays gross

- **WHEN** a position is exited and its realised profit/loss is recorded
- **THEN** that per-position realised profit/loss SHALL be derived from entry and
  exit prices only and SHALL NOT be reduced by the transaction cost

#### Scenario: Existing sessions start at zero fees

- **WHEN** the transaction-cost capability is first deployed
- **THEN** every existing session SHALL have a cumulative transaction-fees total of
  zero and its already-recorded trades SHALL NOT be retroactively charged

### Requirement: Rebalancing prompt informs the agent of transaction costs

The active rebalance prompt SHALL inform the agent that each executed trade incurs
a fixed transaction cost, so that the agent avoids churning small positions when
the expected benefit is below the cost of trading. This SHALL be delivered as a
new rebalance prompt version (per the versioned-prompt requirement); sessions
built after it becomes active SHALL freeze and use it, while already-built
sessions keep their frozen version.

#### Scenario: New sessions freeze the cost-aware prompt

- **WHEN** an AI build creates a session after the cost-aware rebalance prompt
  becomes the active version
- **THEN** the session SHALL freeze that version
- **AND** its rebalances SHALL present the agent with instructions that describe
  the per-trade transaction cost

## MODIFIED Requirements

### Requirement: Live session performance KPIs

The system SHALL expose, on demand for a given paper-trading session, a summary of the session's live performance comprising: the current portfolio value (net asset value: cash plus open positions valued at current market quotes, net of cumulative transaction fees), cumulative realised profit/loss, live unrealised profit/loss on open positions, cumulative transaction fees paid, total return relative to the allocated capital (as both an absolute money amount and a fraction), and a risk-adjusted Sharpe ratio. Requesting the summary SHALL value the session's open positions against current quotes at request time (marking to market on load) rather than returning a stale stored valuation. A request for an unknown session SHALL fail as not found.

#### Scenario: Summary for a session with open positions

- **WHEN** a client requests the KPI summary for an existing session
- **THEN** the system SHALL mark the session's open positions to market and return the current portfolio value (net of transaction fees), realised P&L, unrealised P&L, cumulative transaction fees, total return relative to allocated capital, and the Sharpe ratio (or an unavailable Sharpe when history is insufficient)

#### Scenario: Unknown session

- **WHEN** a client requests the KPI summary for a session id that does not exist
- **THEN** the system SHALL respond with a not-found error and no summary

#### Scenario: Total return relative to allocated capital

- **WHEN** the KPI summary is computed
- **THEN** the total return SHALL be the current portfolio value measured against the session's allocated capital, provided both as an absolute money amount (current value minus allocated capital) and as a fraction of allocated capital

#### Scenario: Cumulative transaction fees reported

- **WHEN** a client requests the KPI summary for a session that has executed trades
- **THEN** the summary SHALL include the session's cumulative transaction fees as a non-negative money amount
