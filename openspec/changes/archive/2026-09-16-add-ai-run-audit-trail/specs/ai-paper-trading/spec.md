## MODIFIED Requirements

### Requirement: Record sessions, trades, runs, and closed positions

The system SHALL persist, per paper-trading session, the executed trades (ticker, side, quantity, price, notional, signal type, order identity and status), a run entry per execution (counts and a trigger and status), and closed positions with realized profit and loss when positions are exited. Each AI build or rebalance SHALL be recorded as an AI-portfolio event capturing the AI's output (its reasoning) and the actions taken, and SHALL also persist the run's research transcript: the web searches performed during the run and, for each, the query and the results the agent received (or a note when a search was not performed, e.g. the per-run search budget was exhausted). Each trade and each closed position produced by an AI build or rebalance SHALL record a reference to the AI-portfolio event that produced it; trades not produced by an AI run SHALL leave this reference empty.

#### Scenario: Trades and run recorded on execution

- **WHEN** a build or rebalance places orders
- **THEN** the system SHALL record a trade per executed order, a run entry summarizing the execution, and (for exits) closed positions with realized P&L

#### Scenario: Trades and closed positions reference their run

- **WHEN** an AI build or rebalance records a trade or a closed position
- **THEN** the recorded trade or closed position SHALL reference the AI-portfolio event that produced it

#### Scenario: Research transcript persisted

- **WHEN** an AI build or rebalance reaches the agent and the agent performs web searches
- **THEN** the recorded AI-portfolio event SHALL persist each search's query and the results the agent received

#### Scenario: Research captured despite a mid-run failure

- **WHEN** an AI run fails after the agent has already performed one or more web searches
- **THEN** the recorded (failed) AI-portfolio event SHALL still persist the research captured before the failure

### Requirement: Read paper-trading session data

The system SHALL let a client list paper-trading sessions and read a session's trades, runs, positions, and its AI-portfolio events. An AI-portfolio event returned to a client SHALL include the AI's reasoning output and its persisted research transcript. A trade or closed position returned to a client SHALL include the reference to the AI-portfolio event that produced it, when present.

#### Scenario: Inspect a session

- **WHEN** a client requests a session's trades, runs, positions, or events
- **THEN** the system SHALL return the recorded data for that session

#### Scenario: Event includes reasoning and research

- **WHEN** a client reads an AI-portfolio event
- **THEN** the returned event SHALL include the AI reasoning output and the persisted research transcript

## ADDED Requirements

### Requirement: Browse AI run history and details

The system SHALL let a client list AI runs (build and rebalance events) across all sessions, ordered newest first, with pagination and optional filtering by run type and status, and SHALL return a total count for the applied filter. The system SHALL let a client open a single AI run by its identifier and receive that run's detail: the run's reasoning output and research transcript, the trades it opened, and the positions it closed (the trades and closed positions referencing that run). Requesting an unknown run identifier SHALL return a not-found error.

#### Scenario: List runs across sessions

- **WHEN** a client requests the AI run list
- **THEN** the system SHALL return AI runs across all sessions ordered newest first, honoring pagination and any type/status filter, together with the matching total count

#### Scenario: Open a run's detail

- **WHEN** a client requests a run by its identifier
- **THEN** the system SHALL return the run's reasoning, its research transcript, the trades it opened, and the positions it closed

#### Scenario: Unknown run

- **WHEN** a client requests a run identifier that does not exist
- **THEN** the system SHALL return a not-found error
