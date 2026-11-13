# order-journal Specification

## Purpose

Guarantee that every order Cadence sends to the broker is durably recorded before it is sent,
can never be executed twice by a retry, is booked into exactly one owner's ledger exactly once
(even across crashes, rollbacks and late fills), and never sells shares the account does not hold.

## Requirements

### Requirement: Write-ahead order recording

Before submitting any order to the broker, the system SHALL record the intended order — its
owner (a strategy bot, an AI portfolio, or the administrator), symbol, asset class, side,
quantity, purpose, and a unique client order id — and SHALL make that record durable
independently of the caller's own unit of work, so that it survives if the caller later fails
or rolls back. The client order id SHALL be sent with the order so the broker can identify it.
After the broker responds, the record SHALL be updated with the broker order id, status, filled
quantity and price, or the submission error. The caller SHALL book a fill into its ledger and
mark the order record as booked in one unit of work, so that a booking and its mark are either
both kept or both discarded. An order record SHALL be booked at most once.

#### Scenario: Order is recorded before it is sent

- **WHEN** the system submits an order
- **THEN** a durable record of the intended order with its client order id SHALL exist before
  the broker receives the order

#### Scenario: Caller failure after the order was sent

- **WHEN** an order is filled at the broker and the caller then fails and discards its unit of
  work
- **THEN** the order record SHALL still exist, unbooked, carrying its client order id

#### Scenario: Booking marks the record

- **WHEN** a caller books a fill into its ledger and its unit of work completes
- **THEN** the order record SHALL be marked booked in the same unit of work

### Requirement: Idempotent resubmission

Every submitted order SHALL carry a client order id that is unique across all orders Cadence
has ever sent. A retry of the same intended order SHALL reuse its client order id, so the broker
refuses a duplicate rather than executing it twice. A new decision to trade (for example a
later tick, or a retry after a definitive rejection) SHALL use a new client order id.

#### Scenario: Duplicate submission is not executed twice

- **WHEN** the same intended order is submitted again with its existing client order id
- **THEN** the broker SHALL execute it at most once

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
before every strategy-bot tick processes its bots, before every AI-portfolio run trades, before
the daily strategy-bot value snapshot records any snapshot (for strategy-bot records), and on
demand. A reconciliation failure during the daily snapshot SHALL NOT prevent the snapshots. A failure to resolve one record SHALL NOT prevent the others from being resolved.
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

#### Scenario: Late-session fill booked before the daily snapshot

- **WHEN** a bot's order sent shortly before the close fills after the bot's last tick, and the
  daily strategy-bot snapshot runs after the close
- **THEN** the fill SHALL be booked into that bot before its snapshot is recorded, so the snapshot
  includes the position and the reduced cash

#### Scenario: Snapshot runs despite a reconciliation failure

- **WHEN** reconciliation fails during the daily strategy-bot snapshot
- **THEN** every active bot SHALL still be snapshotted

### Requirement: Long-only sell guard

The system SHALL refuse to submit any sell order whose quantity exceeds the quantity of that
symbol the broker account currently holds (within a small tolerance). A refused sell SHALL send
no order to the broker, SHALL be recorded as refused, and SHALL be reported to the caller as a
broker-side failure for that order only. The guard SHALL apply to every order path in Cadence.

#### Scenario: Selling more than the account holds is refused

- **WHEN** a sell of 10 shares is requested and the account holds 4
- **THEN** no order SHALL be sent and the caller SHALL receive a refusal

#### Scenario: Selling what the account holds proceeds

- **WHEN** a sell of 4 shares is requested and the account holds 10
- **THEN** the order SHALL be submitted

#### Scenario: Selling a symbol the account does not hold is refused

- **WHEN** a sell is requested for a symbol the account holds none of
- **THEN** no order SHALL be sent

### Requirement: Single order path

Every order Cadence submits — strategy-bot entries and exits, stopped-bot flattening, AI-portfolio
build, rebalance, close, stop-loss and scope-change liquidation, and administrator actions —
SHALL go through write-ahead recording and the long-only sell guard. No component SHALL submit
an order to the broker by any other route.

#### Scenario: Every path is recorded

- **WHEN** any of the listed components submits an order
- **THEN** an order record with a client order id SHALL exist for it

### Requirement: Administrator rejections are closed at once

When the broker explicitly rejects an administrator order, its journal record SHALL be closed
immediately without booking anything, because administrator orders have no ledger; it SHALL NOT
appear among unresolved orders. An administrator order whose outcome is unknown (for example a
timeout) SHALL remain for reconciliation.

#### Scenario: Rejected admin order is not left unresolved

- **WHEN** the broker rejects a Restore purchase
- **THEN** the order's record SHALL be closed and SHALL NOT be listed as unresolved
