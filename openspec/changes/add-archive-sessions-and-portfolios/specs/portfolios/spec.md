## ADDED Requirements

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
