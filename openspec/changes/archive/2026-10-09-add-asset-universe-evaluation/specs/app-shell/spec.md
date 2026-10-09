## ADDED Requirements

### Requirement: Asset universe AI evaluation panel

The Assets page SHALL render an AI universe evaluation panel directly below the
asset-composition donut charts. The panel SHALL show the evaluation's markdown
narrative and its bulleted key findings together with the time it was generated,
SHALL display a clear outdated warning when the universe has changed since the
evaluation was generated, and SHALL provide a refresh control that regenerates the
evaluation. When no evaluation exists yet, the panel SHALL trigger generation on
first load and show a generating state until it completes.

#### Scenario: Panel renders the evaluation under the donuts

- **WHEN** the Assets page loads and a current evaluation exists
- **THEN** a panel below the composition donuts shows the narrative, the key
  findings, and the time the evaluation was generated

#### Scenario: Outdated warning

- **WHEN** the current evaluation is reported as outdated
- **THEN** the panel displays a warning that the asset universe has changed since
  the evaluation was generated

#### Scenario: No warning when current

- **WHEN** the current evaluation is not outdated
- **THEN** the panel shows no outdated warning

#### Scenario: Manual refresh

- **WHEN** the operator activates the refresh control
- **THEN** the panel regenerates the evaluation, shows a loading state while it runs
  with the control disabled, and replaces the displayed evaluation when it completes

#### Scenario: First-load generation when empty

- **WHEN** the Assets page loads and no evaluation has ever been generated
- **THEN** the panel triggers generation and shows a generating state until the
  evaluation is available
