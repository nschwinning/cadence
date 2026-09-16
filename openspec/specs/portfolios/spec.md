# portfolios Specification

## Purpose
Persists AI-managed portfolios — named baskets of tickers with a risk profile and allocation cap — so that paper-trading sessions have a stable, retrievable definition of what an AI portfolio contains and where it came from.

## Requirements

### Requirement: Create a portfolio

The system SHALL create a portfolio with a name, a non-empty set of tickers, an allocation cap (a fraction in the range 0 < cap ≤ 1), a source classification, and an optional risk profile and description. Tickers SHALL be normalized (trimmed, uppercased). The system SHALL reject a portfolio with no tickers or an out-of-range allocation cap.

#### Scenario: Create a valid portfolio

- **WHEN** a client creates a portfolio with a name and at least one ticker
- **THEN** the system SHALL persist it with normalized tickers and respond with the stored portfolio including its generated identifier

#### Scenario: Reject an empty portfolio

- **WHEN** a client creates a portfolio with zero tickers or an allocation cap outside 0 < cap ≤ 1
- **THEN** the system SHALL respond with a validation error and SHALL NOT persist it

### Requirement: Retrieve portfolios

The system SHALL allow listing all portfolios and fetching a single portfolio by its identifier, including its tickers, risk profile, allocation cap, and source.

#### Scenario: List portfolios

- **WHEN** a client requests the portfolio list
- **THEN** the system SHALL return all portfolios with their attributes

#### Scenario: Fetch a portfolio by id

- **WHEN** a client requests an existing portfolio by id
- **THEN** the system SHALL return that portfolio; for an unknown id it SHALL respond 404

### Requirement: Update the tickers of an AI-managed portfolio

The system SHALL allow the set of tickers in a portfolio to be updated (for example when a rebalance changes the holdings), enforcing the same non-empty and normalization rules as creation.

#### Scenario: Holdings change after a rebalance

- **WHEN** the holdings of an AI-managed portfolio change
- **THEN** the system SHALL update the stored ticker set with normalized values, keeping the portfolio identity unchanged

### Requirement: Archive a portfolio

The system SHALL let a client archive a portfolio and later unarchive it. Archiving
SHALL be a reversible, non-destructive state: an archived portfolio retains its
definition (name, tickers, risk profile, allocation cap, source) and its associated
paper-trading sessions, and can be restored. A portfolio SHALL be considered archived
when, and only when, it carries an archive timestamp.

The system SHALL allow archiving a portfolio only when none of its paper-trading
sessions is active or paused — that is, every session belonging to it is stopped (or
itself archived), or it has no sessions at all. A request to archive a portfolio that
still has an active or paused session SHALL be rejected without changing the
portfolio. Unarchiving SHALL clear the archive timestamp and SHALL be allowed for any
archived portfolio. Archiving or unarchiving an unknown portfolio SHALL respond 404.

#### Scenario: Archive a portfolio with no active sessions

- **WHEN** a client archives a portfolio whose sessions are all stopped, or which has
  no sessions
- **THEN** the system SHALL mark the portfolio archived and retain its definition and
  sessions

#### Scenario: Reject archiving a portfolio with an active session

- **WHEN** a client attempts to archive a portfolio that has an active or paused
  session
- **THEN** the system SHALL reject the request and SHALL leave the portfolio
  unarchived

#### Scenario: Unarchive a portfolio

- **WHEN** a client unarchives an archived portfolio
- **THEN** the system SHALL clear its archived state and return it to the default
  portfolio list

#### Scenario: Archive an unknown portfolio

- **WHEN** a client archives or unarchives a portfolio id that does not exist
- **THEN** the system SHALL respond 404

### Requirement: Archive-aware portfolio listing

The system SHALL exclude archived portfolios from the default portfolio list, and
SHALL provide a way to include archived portfolios on request. When archived
portfolios are included, each portfolio returned SHALL carry its archived state so a
client can distinguish archived from active rows.

#### Scenario: Default list hides archived portfolios

- **WHEN** a client lists portfolios without asking for archived rows
- **THEN** the system SHALL return only portfolios that are not archived

#### Scenario: Include archived portfolios on request

- **WHEN** a client lists portfolios and opts to include archived rows
- **THEN** the system SHALL return both archived and non-archived portfolios, each
  indicating its archived state
