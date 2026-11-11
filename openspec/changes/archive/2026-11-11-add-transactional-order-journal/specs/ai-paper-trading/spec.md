## ADDED Requirements

### Requirement: AI-portfolio orders are journaled and reconciled before each run

Every order an AI portfolio submits — during build, rebalance, close, stop-loss and scope-change
liquidation — SHALL be recorded before submission and booked through the order journal, so that
an order whose run fails after submission is still booked into that portfolio exactly once by
reconciliation. Before an AI-portfolio run submits any order, the system SHALL reconcile that
portfolio's unresolved orders. An AI-portfolio sell SHALL be refused, sending no order, when the
account holds fewer units than the sell quantity; the refusal SHALL be reported for that order
only and SHALL NOT abort the run.

#### Scenario: Run fails after submitting orders

- **WHEN** an AI rebalance submits orders and then fails before completing
- **THEN** the submitted orders' fills SHALL later be booked into that portfolio exactly once

#### Scenario: Reconciliation precedes trading

- **WHEN** an AI-portfolio run starts while the portfolio has an unresolved order
- **THEN** that order SHALL be reconciled before the run submits new orders

#### Scenario: Oversized AI sell is refused

- **WHEN** an AI rebalance wants to sell more units than the account holds
- **THEN** no order SHALL be sent for that sell, it SHALL be reported as not executed, and the
  rest of the run SHALL proceed
