## MODIFIED Requirements

### Requirement: Queue a recommendation run

The system SHALL accept a request to generate asset recommendations specifying how many assets are wanted and optionally which categories to target. Supported categories are restricted to **stock** and **crypto**; a request naming any other category SHALL be rejected. The system SHALL create a run in a queued state and return immediately (202) with the run's identifier and status, without blocking on the AI. Only one recommendation run SHALL execute at a time; if a run is already in flight, the system SHALL return the in-flight run rather than starting a second.

#### Scenario: Queue a run

- **WHEN** a client requests recommendations with a valid requested count and supported categories (stock and/or crypto)
- **THEN** the system SHALL create a queued run and respond 202 with the run id and status

#### Scenario: Reject an invalid request

- **WHEN** a client requests recommendations with an invalid count, or a category other than stock or crypto
- **THEN** the system SHALL respond 422 and SHALL NOT create a run

#### Scenario: A run is already in progress

- **WHEN** a client queues a run while another run is still executing
- **THEN** the system SHALL return the already-running run and SHALL NOT start a concurrent run

## ADDED Requirements

### Requirement: Recommendations exclude assets already in the universe

The recommender SHALL be given the set of tickers already present in the universe
and SHALL be instructed not to propose any of them. The system SHALL still
de-duplicate server-side as a safety net, so an asset already in the universe is
never added twice regardless of what the agent returns.

#### Scenario: Existing tickers are excluded in the prompt

- **WHEN** a recommendation run starts while the universe already holds assets
- **THEN** the prompt sent to the agent SHALL list those tickers as excluded and
  instruct the agent not to propose them

#### Scenario: A duplicate is never added

- **WHEN** the agent nonetheless proposes a ticker already in the universe
- **THEN** the system SHALL skip it as a duplicate rather than adding it again
