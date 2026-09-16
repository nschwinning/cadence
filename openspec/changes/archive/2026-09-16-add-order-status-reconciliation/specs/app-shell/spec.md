## ADDED Requirements

### Requirement: Session detail syncs order state until terminal

When a user opens a paper-trading session's detail view, the UI SHALL request a
reconciliation of that session's order state so that displayed order statuses reflect
the latest broker information rather than only what was known at submission. While any
of the session's orders is in a non-terminal status, the UI SHALL keep refreshing the
session's order state on a recurring interval, and it SHALL stop refreshing once every
order has reached a terminal status. Reconciled statuses, fill prices, and updated
position values SHALL become visible without requiring a manual page reload.

#### Scenario: Reconcile on opening the session detail view

- **WHEN** a user opens a session's detail view
- **THEN** the UI SHALL request reconciliation of that session's orders and SHALL
  display the resulting order statuses and fills

#### Scenario: Poll while orders are non-terminal

- **WHEN** the session's detail view is open and at least one order is in a
  non-terminal status
- **THEN** the UI SHALL continue refreshing the session's order state on a recurring
  interval and reflect updates without a manual reload

#### Scenario: Stop polling once all orders are terminal

- **WHEN** every order in the open session has reached a terminal status
- **THEN** the UI SHALL stop the recurring refresh
