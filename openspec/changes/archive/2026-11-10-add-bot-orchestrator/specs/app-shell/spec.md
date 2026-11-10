## ADDED Requirements

### Requirement: Bot orchestrator navigation entry

The application shell SHALL provide an "Orchestrators" navigation entry, placed directly
after the "Bots" entry, leading to the bot-orchestrator area (its list, deploy form and
detail views). The entry SHALL indicate when it is the active view, like the other
navigation entries.

#### Scenario: Orchestrators entry follows Bots

- **WHEN** a user views the sidebar navigation
- **THEN** it SHALL show an "Orchestrators" entry directly after the "Bots" entry

#### Scenario: Orchestrators entry opens the orchestrator area

- **WHEN** a user selects the "Orchestrators" entry
- **THEN** the shell SHALL show the orchestrator list view and mark the entry as active
