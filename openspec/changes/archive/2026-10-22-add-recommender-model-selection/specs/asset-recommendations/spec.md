## ADDED Requirements

### Requirement: Select the AI model for a recommendation run

A recommendation-run request (universe or watchlist target) MAY specify the AI
`model` to run on, chosen from the shared AI model catalog. When the request omits
a model, the system SHALL use the configured default recommender model. A request
naming a model that is not in the catalog SHALL be rejected (422) without creating
a run. The system SHALL persist the resolved model on the run, SHALL execute the
run on that model, and SHALL report it on the run's status so every run records
which model produced its candidates. This applies identically to both the
universe (asset) recommender and the watchlist recommender, which share one agent.

#### Scenario: Run uses the selected model

- **WHEN** a client queues a recommendation run specifying a model that is in the
  catalog
- **THEN** the system SHALL create the run with that model, execute the agent on
  it, and report that model on the run's status

#### Scenario: Run defaults to the configured model

- **WHEN** a client queues a recommendation run without specifying a model
- **THEN** the system SHALL resolve the run's model to the configured default
  recommender model and report it on the run's status

#### Scenario: Unknown model is rejected

- **WHEN** a client queues a recommendation run naming a model that is not in the
  catalog
- **THEN** the system SHALL respond 422 and SHALL NOT create a run

#### Scenario: Watchlist run honours the selected model

- **WHEN** a client queues a watchlist-targeted run specifying a catalog model
- **THEN** the system SHALL execute the watchlist run on that model and report it
  on the run's status, the same as a universe run
