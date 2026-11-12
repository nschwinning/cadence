## ADDED Requirements

### Requirement: Crypto holdings follow the broker's coin-denominated fee

Because the broker charges its crypto buy fee in the coin received, the system SHALL record an
AI portfolio's crypto buy in its ledger at the quantity actually received — the filled quantity
reduced by the configured crypto fee rate — at the filled price, while still charging the fee to
the session's fees exactly once. The recorded trade SHALL keep the filled quantity. An
AI-portfolio crypto sell SHALL be capped at the quantity the broker account holds of that coin,
so a full exit is never refused because the ledger is marginally above the holding. Equity
booking SHALL be unchanged.

#### Scenario: Crypto buy is booked net of the fee

- **WHEN** an AI portfolio buys 1,000 ADA at $0.50 with a 0.25% crypto fee rate
- **THEN** its ledger SHALL hold 997.5 ADA at an average cost of $0.50, the trade SHALL record
  1,000 ADA, and the session's fees SHALL increase by $1.25

#### Scenario: Full crypto exit is capped at the holding

- **WHEN** an AI portfolio exits a coin whose ledger quantity is 0.0001 above the account's
  holding
- **THEN** the sell SHALL be submitted for the account's holding and SHALL NOT be refused

#### Scenario: Equity booking is unchanged

- **WHEN** an AI portfolio buys an equity
- **THEN** its ledger SHALL record the filled quantity

### Requirement: Broker minimum for crypto orders

The system SHALL NOT submit a crypto order worth less than $10 (the broker's minimum crypto order
value) from an AI-portfolio run; such a trade SHALL be skipped and reported as below the minimum.

#### Scenario: Tiny crypto rebalance is skipped

- **WHEN** a rebalance would buy $6 of SOL
- **THEN** no order SHALL be sent and the trade SHALL be reported as below the $10 minimum
