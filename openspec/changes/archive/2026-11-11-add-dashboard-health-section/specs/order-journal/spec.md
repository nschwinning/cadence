## MODIFIED Requirements

### Requirement: Reconcile unbooked orders

The system SHALL resolve every order record that is not booked and whose owner is no longer
working on it (its lease has expired) by looking the order up at the broker by its client order
id, and SHALL then:

- book the filled quantity at the filled price into the owning strategy bot or AI portfolio
  exactly once, recording the trade and updating its positions, cash and realised profit/loss as
  a normal fill would, and mark the record booked;
- close out without booking a record the broker rejected, cancelled or expired with nothing
  filled, or never received;
- leave a record whose order is still working at the broker unbooked for a later pass.

Administrator orders SHALL be marked booked without any ledger change. Reconciliation SHALL run
before every strategy-bot tick processes its bots, before every AI-portfolio run trades, and on
demand. A failure to resolve one record SHALL NOT prevent the others from being resolved.
When the broker explicitly rejects a submission, the owner's lease on that record SHALL end
immediately, so the next reconciliation pass confirms there is nothing to book and the owner is
not kept from trading the symbol for the rest of the lease; a submission whose outcome is unknown
(for example a timeout) SHALL keep its lease.

#### Scenario: Fill lost to a rollback is booked once

- **WHEN** a bot's order filled but the tick that sent it rolled back, and reconciliation runs
- **THEN** the fill SHALL be booked into that bot exactly once and the record marked booked

#### Scenario: Late fill after a poll timeout

- **WHEN** a bot's order was still working when the engine stopped waiting, and it fills later
- **THEN** a later reconciliation SHALL book the fill into that bot

#### Scenario: Order never reached the broker

- **WHEN** the broker has no order with the record's client order id and its lease has expired
- **THEN** the record SHALL be closed out without booking anything

#### Scenario: Reconciliation is idempotent

- **WHEN** reconciliation runs twice over the same resolved record
- **THEN** nothing SHALL be booked the second time

#### Scenario: In-flight order is left alone

- **WHEN** reconciliation runs while the owner is still within its lease on a record
- **THEN** the record SHALL NOT be touched

#### Scenario: Explicit rejection is handed over at once

- **WHEN** the broker explicitly rejects a bot's order
- **THEN** the next reconciliation pass SHALL close the record without waiting for the lease, and
  the bot SHALL be free to submit a new order for that symbol in the same tick
