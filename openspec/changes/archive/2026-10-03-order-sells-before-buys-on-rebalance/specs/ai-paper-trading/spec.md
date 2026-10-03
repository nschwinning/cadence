## ADDED Requirements

### Requirement: Rebalance submits sells before buys and gates buys on sell fills

During a rebalance, the system SHALL submit every sell (including full exits) before it submits any buy, and SHALL submit the buys only after the submitted sells have reached a terminal order state at the brokerage. Terminal states are filled, cancelled, and rejected; a cancelled or rejected sell counts as settled so it never blocks the run, and a rebalance with no sells to place SHALL proceed directly to its buys. The buys SHALL be submitted together once the sells have settled, rather than interleaved with the sells. This ordering guarantee holds regardless of the order in which tickers would otherwise be processed.

The wait for sells to settle SHALL be bounded by a configured timeout. If the timeout elapses before the submitted sells settle, the system SHALL NOT submit the dependent buys for that run; it SHALL record each withheld buy as not executed with a reason indicating the sells had not yet filled, and SHALL leave the executed sells in place so a later rebalance redeploys the freed cash. The system SHALL retry an order the brokerage rejects, up to a bounded number of attempts within the same run, before recording it as not executed.

All existing rebalance behavior SHALL be preserved: crypto-only scope, skipping equity orders while the equities market is closed, the risk-guardrail weight clamp, sizing against the session's current value, fractional crypto / whole-share equity sizing, and the recorded trade shape. When the brokerage fills orders synchronously (the offline stub), the submitted sells settle immediately and the buys proceed within the same run.

#### Scenario: Sells are submitted before any buy

- **WHEN** a rebalance needs to both sell some holdings and buy others
- **THEN** the system SHALL submit all of the sell orders before it submits any buy order

#### Scenario: Buys wait until sells have settled

- **WHEN** the sell orders have been submitted but have not yet reached a terminal state at the brokerage
- **THEN** the system SHALL withhold the buy orders until every submitted sell reaches a terminal state (filled, cancelled, or rejected)

#### Scenario: Synchronous broker completes the rebalance in one run

- **WHEN** the brokerage fills orders synchronously (the offline stub)
- **THEN** the submitted sells SHALL settle immediately and the system SHALL submit the buys in the same run, with the freed cash available to fund them

#### Scenario: Rebalance with no sells proceeds to buys

- **WHEN** a rebalance has only buy orders and no sells to place
- **THEN** the system SHALL submit the buys without waiting, since there is nothing to settle

#### Scenario: Fill-wait timeout withholds buys without failing the run

- **WHEN** the submitted sells do not settle before the configured fill-wait timeout elapses (for example, sells placed while the equities market is closed)
- **THEN** the system SHALL skip the dependent buys for that run, record each withheld buy as not executed with a "sells not yet filled" reason, and keep the executed sells so a later rebalance redeploys the freed cash

#### Scenario: Rejected order is retried

- **WHEN** the brokerage rejects a submitted order
- **THEN** the system SHALL resubmit it up to the bounded retry limit within the same run before recording it as not executed
