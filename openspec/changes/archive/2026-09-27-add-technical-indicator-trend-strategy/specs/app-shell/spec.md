## MODIFIED Requirements

### Requirement: AI run history and detail views

The system SHALL provide a Runs view that lists AI runs (build and rebalance) across all sessions, newest first, showing at least each run's type, status, number of orders executed, and time, and SHALL let a user open a run to a detail view. The run detail view SHALL show the run's AI reasoning, its research (each web search's query and results), the trades the run opened, the positions the run closed, and — when the run recorded trend-decision context — the technical-indicator picture behind the run: the candidates that were filtered out by the trend gate (each with the reason it failed) and the indicator annotations that were handed to the AI for the surviving candidates and for the current holdings (including the holdings' reversal flags). When a run recorded no trend-decision context, the detail view SHALL simply omit that section rather than show an error.

#### Scenario: Browse runs

- **WHEN** a user opens the Runs view
- **THEN** the UI SHALL list AI runs across all sessions newest first and allow opening any run's detail

#### Scenario: Inspect a run

- **WHEN** a user opens a run's detail
- **THEN** the UI SHALL display the run's reasoning, its research (queries and results), the trades it opened, and the positions it closed

#### Scenario: Inspect a run's trend-decision context

- **WHEN** a user opens the detail of a run that recorded trend-decision context
- **THEN** the UI SHALL display the candidates filtered out by the trend gate with their reasons and the indicator annotations handed to the AI for the surviving candidates and the holdings (with reversal flags)

#### Scenario: Run without trend-decision context

- **WHEN** a user opens the detail of a run that recorded no trend-decision context
- **THEN** the UI SHALL omit the trend-decision section without error
