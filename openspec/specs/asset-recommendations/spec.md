# asset-recommendations Specification

## Purpose
Lets a user ask an AI to discover candidate tickers worth adding to the universe, validating each candidate through the same eligibility gate as manual additions, so the universe can grow without manual research.

## Requirements

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

### Requirement: Execute a recommendation run and add eligible assets

The system SHALL progress a run through observable phases (queued → searching → validating → completed, or failed) and record the exact prompt used, the number of AI tool calls, and per-candidate outcomes. During validation each candidate SHALL be added through the standard asset-eligibility path; ineligible or duplicate candidates SHALL be recorded with their outcome and SHALL NOT be added. The run SHALL stop adding once the requested count of eligible assets is reached.

#### Scenario: Run completes and adds eligible candidates

- **WHEN** the AI returns candidates and validation runs
- **THEN** the system SHALL add eligible, non-duplicate candidates up to the requested count, record each candidate's outcome, and mark the run completed

#### Scenario: Run fails

- **WHEN** the AI call errors or times out
- **THEN** the system SHALL mark the run failed with a recorded reason and SHALL leave the universe unchanged except for candidates already validated

### Requirement: Poll recommendation run status

The system SHALL let a client list recommendation runs newest-first and fetch a single run's status by id. A run whose background worker has died without reaching a terminal phase SHALL be reported as failed.

#### Scenario: Poll until terminal

- **WHEN** a client fetches a run's status repeatedly
- **THEN** the system SHALL report the current phase and, once finished, a terminal phase with the per-candidate outcomes

#### Scenario: Unknown run

- **WHEN** a client fetches a run id that does not exist
- **THEN** the system SHALL respond 404

### Requirement: Offline stub mode

The system SHALL support an offline mode (selectable by configuration) in which recommendations are produced without any external AI or web-search calls, while still routing every candidate through the real eligibility validation.

#### Scenario: Stub mode enabled

- **WHEN** offline stub mode is enabled and a run is queued
- **THEN** the system SHALL generate candidates without external calls and validate them through the normal eligibility path

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
