## Purpose

Persists AI-managed portfolios — named baskets of tickers with a risk profile and allocation cap — so that paper-trading sessions have a stable, retrievable definition of what an AI portfolio contains and where it came from.

## ADDED Requirements

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
