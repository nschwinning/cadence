## ADDED Requirements

### Requirement: Increase a session's capital from the detail view

The paper-trading session detail view SHALL present, alongside the session's capital fact, a control that lets the user increase the session's capital by a positive amount. The control SHALL accept an amount, SHALL only permit increases (it SHALL NOT offer a withdrawal or a non-positive amount), and on confirmation SHALL request the increase. On success the UI SHALL refresh the session's capital-dependent figures (at least the displayed capital, the session's value and performance KPI tiles, and the value-history chart) so the added capital and its effect on returns are reflected. While the request is in flight the control SHALL indicate progress, and a failed request SHALL surface an error without leaving the view in an inconsistent state.

#### Scenario: Add capital from the detail view

- **WHEN** a user enters a positive amount in the add-capital control on the session detail view and confirms
- **THEN** the UI SHALL request the increase and, on success, refresh the displayed capital, the session's value/KPI tiles, and the value-history chart

#### Scenario: Non-positive amount is not submitted

- **WHEN** a user enters zero, a negative amount, or no amount in the add-capital control
- **THEN** the UI SHALL NOT request an increase

#### Scenario: In-flight progress indicated

- **WHEN** a capital-increase request is in flight
- **THEN** the control SHALL indicate progress

#### Scenario: Failed increase surfaces an error

- **WHEN** a capital-increase request fails
- **THEN** the UI SHALL surface an error and leave the session's displayed capital unchanged
