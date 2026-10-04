## ADDED Requirements

### Requirement: Show and switch a session's asset scope from the detail view

The paper-trading session detail view SHALL display the session's current asset scope (stocks, crypto, or both) as a labeled fact alongside the session's other configuration facts. The detail view SHALL let the user change the session's scope to any supported scope at any time, presenting the available scopes for selection with the session's current scope shown as selected. When the selected scope change would liquidate currently-held positions — a narrowing that excludes the asset class of one or more open positions — the UI SHALL warn the user that those holdings will be sold and SHALL require the user to explicitly confirm before the change is requested; if the user does not confirm, no change SHALL be requested and the session's displayed scope SHALL remain unchanged. A scope change that would liquidate nothing (a widening, or a narrowing that excludes no held position) SHALL NOT require such a warning. On confirming a change, the UI SHALL request the change and, on success, refresh the session's scope-dependent figures (at least the displayed scope and the session's value and KPI figures, which a narrowing liquidation can move). While the change is in flight the control SHALL indicate progress, and a failed change SHALL surface an error without leaving the view in an inconsistent state.

#### Scenario: Scope shown on the detail view

- **WHEN** a user opens a paper-trading session's detail view
- **THEN** the view SHALL display the session's current asset scope (stocks, crypto, or both)

#### Scenario: Change the scope from the detail view

- **WHEN** a user selects a different scope on the session detail view and confirms
- **THEN** the UI SHALL request the change and, on success, refresh the displayed scope and the session's value/KPI figures

#### Scenario: Warn and confirm before a narrowing that liquidates holdings

- **WHEN** a user selects a scope change that would sell one or more currently-held positions whose asset class the new scope excludes
- **THEN** the UI SHALL warn the user that those holdings will be liquidated and SHALL request the change only after the user explicitly confirms

#### Scenario: Declining the warning cancels the change

- **WHEN** the UI warns about a liquidating scope change and the user does not confirm
- **THEN** the UI SHALL NOT request the change and the session's displayed scope SHALL remain unchanged

#### Scenario: Non-liquidating change needs no warning

- **WHEN** a user selects a scope change that would sell no currently-held position (a widening, or a narrowing that excludes nothing held)
- **THEN** the UI SHALL request the change without requiring a liquidation warning

#### Scenario: Current scope preselected

- **WHEN** a user opens the scope control on the session detail view
- **THEN** the control SHALL present the supported scopes with the session's current scope selected

#### Scenario: Failed change surfaces an error

- **WHEN** a scope change request fails
- **THEN** the UI SHALL surface an error and leave the session's displayed scope unchanged
