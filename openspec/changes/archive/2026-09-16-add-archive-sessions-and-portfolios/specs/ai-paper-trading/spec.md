## ADDED Requirements

### Requirement: Archive a stopped paper-trading session

The system SHALL let a client archive a paper-trading session and later unarchive
it. Archiving SHALL be a reversible, non-destructive state: an archived session
retains all of its data (trades, runs, positions, events, value snapshots) and can
be restored. A session SHALL be considered archived when, and only when, it carries
an archive timestamp.

The system SHALL allow archiving only a session whose status is stopped; a request
to archive an active or paused session SHALL be rejected without changing the
session. Unarchiving SHALL clear the archive timestamp and SHALL be allowed for any
archived session regardless of its status. Archiving or unarchiving an unknown
session SHALL respond 404.

Archiving and unarchiving SHALL change only the session's archived state; they SHALL
NOT alter the session's status or delete any related data.

#### Scenario: Archive a stopped session

- **WHEN** a client archives a session whose status is stopped
- **THEN** the system SHALL mark the session archived and retain all of its trades,
  runs, positions, events, and value snapshots

#### Scenario: Reject archiving a non-stopped session

- **WHEN** a client attempts to archive a session whose status is active or paused
- **THEN** the system SHALL reject the request and SHALL leave the session
  unarchived

#### Scenario: Unarchive a session

- **WHEN** a client unarchives an archived session
- **THEN** the system SHALL clear its archived state and return it to the default
  session list, without changing its status

#### Scenario: Archive an unknown session

- **WHEN** a client archives or unarchives a session id that does not exist
- **THEN** the system SHALL respond 404

### Requirement: Archive-aware session listing

The system SHALL exclude archived sessions from the default session list, and SHALL
provide a way to include archived sessions on request. When archived sessions are
included, each session returned SHALL carry its archived state so a client can
distinguish archived from active rows. The archived filter SHALL compose with the
existing status filter.

#### Scenario: Default list hides archived sessions

- **WHEN** a client lists paper-trading sessions without asking for archived rows
- **THEN** the system SHALL return only sessions that are not archived

#### Scenario: Include archived sessions on request

- **WHEN** a client lists paper-trading sessions and opts to include archived rows
- **THEN** the system SHALL return both archived and non-archived sessions, each
  indicating its archived state
