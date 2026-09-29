## ADDED Requirements

### Requirement: Multi-session comparison value history read

The system SHALL provide a read that returns, in a single response, the value history of multiple paper-trading sessions so they can be compared over time. The response SHALL include **every non-archived session** (active, paused, or stopped) — the same set as the default session listing, excluding soft-archived sessions. For each included session the response SHALL carry: a stable session identifier, a display **label** (the session's portfolio name, falling back to its strategy key when the portfolio name is unresolved), its **allocated capital**, and its ordered list of value **points** — each point exposing at least the snapshot date and the session's total portfolio value on that date — sorted oldest date first. A session that has no value snapshots yet SHALL still be included with an empty points list. The read SHALL NOT require or accept a per-session identifier as input (it returns the comparison set as a whole).

#### Scenario: Comparison read returns each non-archived session's series

- **WHEN** a client requests the multi-session comparison value history and multiple non-archived sessions exist, each with value snapshots
- **THEN** the response SHALL contain one entry per non-archived session, each carrying the session's identifier, label, allocated capital, and its value points ordered oldest date first

#### Scenario: Archived sessions are excluded

- **WHEN** a client requests the multi-session comparison value history and one or more sessions are archived
- **THEN** the response SHALL omit every archived session and include only the non-archived ones

#### Scenario: Session without snapshots is included with no points

- **WHEN** a client requests the multi-session comparison value history and a non-archived session has no value snapshots yet
- **THEN** the response SHALL still include that session with its identifier, label, and allocated capital, and an empty list of points

#### Scenario: Session label falls back to the strategy key

- **WHEN** a session in the comparison read has no resolvable portfolio name
- **THEN** that session's label SHALL be its strategy key rather than an empty value
