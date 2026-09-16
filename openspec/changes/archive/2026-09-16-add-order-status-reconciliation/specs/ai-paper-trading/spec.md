## ADDED Requirements

### Requirement: Reconcile a session's order status against the broker

The system SHALL reconcile a paper-trading session's recorded trades against the
broker until each trade reaches a terminal order status. For each of the session's
trades that carries a broker order id and whose recorded order status is not yet
terminal, the system SHALL query the broker for the current state of that order and
SHALL update the trade's recorded order status, filled price, and filled time to
match the broker's current values. Terminal order statuses (filled, cancelled,
rejected) SHALL NOT be re-queried, and a trade without a broker order id SHALL be
left unchanged.

If the broker cannot be reached or does not recognise an order, that trade SHALL be
left unchanged and reconciliation of the remaining trades SHALL continue; a
transient broker failure SHALL NOT corrupt or discard already-recorded trade data.

Reconciling an unknown session SHALL respond 404.

#### Scenario: A pending order fills

- **WHEN** a session is reconciled and one of its trades — recorded as non-terminal
  — is now reported by the broker as filled at a known price and time
- **THEN** the system SHALL update that trade's order status to filled and record
  the broker's fill price and fill time

#### Scenario: Terminal trades are not re-queried

- **WHEN** a session is reconciled and a trade is already in a terminal order status
- **THEN** the system SHALL leave that trade unchanged and SHALL NOT query the broker
  for it

#### Scenario: A trade without a broker order id is skipped

- **WHEN** a session is reconciled and a non-terminal trade has no broker order id
- **THEN** the system SHALL leave that trade unchanged

#### Scenario: Broker unavailable during reconciliation

- **WHEN** the broker cannot be reached or does not recognise an order while a session
  is being reconciled
- **THEN** the system SHALL leave the affected trade unchanged, SHALL continue
  reconciling the session's other trades, and SHALL NOT discard existing trade data

#### Scenario: Reconcile an unknown session

- **WHEN** a client reconciles a session id that does not exist
- **THEN** the system SHALL respond 404

### Requirement: Correct ledger cost basis from actual fills

When reconciliation of a buy trade produces a fill price that differs from the price
recorded for that trade at submission, the system SHALL correct the session's
open-position cost basis for that ticker so that the position's average cost reflects
the actual fill price rather than the pre-trade estimate. If the reconciled fill
price equals the previously recorded price, the cost basis SHALL be left unchanged.

#### Scenario: Fill price differs from the submitted estimate

- **WHEN** a buy trade is reconciled and the broker's actual fill price differs from
  the price recorded for that trade at submission, and the ticker is still held
- **THEN** the system SHALL adjust the open position's average cost so it reflects the
  actual fill price

#### Scenario: Fill price matches the estimate

- **WHEN** a buy trade is reconciled and the broker's fill price equals the price
  already recorded for that trade
- **THEN** the system SHALL leave the open position's cost basis unchanged

### Requirement: Scheduled reconciliation of all sessions' open orders

The system SHALL provide a scheduled entry point that reconciles the non-terminal
orders of every paper-trading session, so that order state and cost basis resolve
even when no client is viewing a session. This entry point SHALL be protected by the
same cron authorization used by other scheduled operations and SHALL reject requests
lacking a valid cron token. A failure to reconcile one session SHALL NOT prevent the
remaining sessions from being reconciled, and the operation SHALL report how many
sessions and trades were reconciled.

#### Scenario: Cron reconciles open orders across sessions

- **WHEN** the scheduled reconciliation entry point is invoked with a valid cron token
- **THEN** the system SHALL reconcile the non-terminal orders of all sessions and
  SHALL report the sessions and trades it reconciled

#### Scenario: Cron request without a valid token is rejected

- **WHEN** the scheduled reconciliation entry point is invoked without a valid cron
  token
- **THEN** the system SHALL reject the request and SHALL NOT reconcile any session

#### Scenario: One session's failure does not stop the rest

- **WHEN** reconciling one session fails during a scheduled run
- **THEN** the system SHALL continue reconciling the remaining sessions
