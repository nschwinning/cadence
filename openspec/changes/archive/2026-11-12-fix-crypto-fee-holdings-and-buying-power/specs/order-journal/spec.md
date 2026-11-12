## ADDED Requirements

### Requirement: Administrator rejections are closed at once

When the broker explicitly rejects an administrator order, its journal record SHALL be closed
immediately without booking anything, because administrator orders have no ledger; it SHALL NOT
appear among unresolved orders. An administrator order whose outcome is unknown (for example a
timeout) SHALL remain for reconciliation.

#### Scenario: Rejected admin order is not left unresolved

- **WHEN** the broker rejects a Restore purchase
- **THEN** the order's record SHALL be closed and SHALL NOT be listed as unresolved
