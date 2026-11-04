## ADDED Requirements

### Requirement: Paginated trade-ledger reads

The system SHALL expose a bot session's trade ledger through a paginated read API.
A request MAY specify a zero-based `offset` and a `limit`; the system SHALL default
the limit to 20 and SHALL reject a limit above 100 or a negative offset/limit with a
`422` response. The system SHALL return a single page of trades ordered by execution
time most-recent-first, together with the full count of the session's trades so the
client can determine how many pages exist. The system SHALL NOT require loading the
entire ledger into memory to serve a page. An unknown session SHALL return `404`.

#### Scenario: Default page returns the most recent trades

- **WHEN** a client requests a known session's trades without pagination parameters
- **THEN** the system SHALL return at most the default page size of trades, ordered
  most-recent-first, and a `total` equal to the session's full trade count

#### Scenario: Offset and limit select a bounded page

- **WHEN** a client requests a known session's trades with a valid `offset` and
  `limit`
- **THEN** the system SHALL return only the trades in that window, still ordered
  most-recent-first, with `total` unchanged as the full count

#### Scenario: Invalid pagination parameters are rejected

- **WHEN** a client requests trades with a negative offset or limit, or a limit above
  the maximum of 100
- **THEN** the system SHALL respond with `422` and SHALL NOT return a page

#### Scenario: Unknown session

- **WHEN** a client requests trades for a session id that does not exist
- **THEN** the system SHALL respond with `404`
