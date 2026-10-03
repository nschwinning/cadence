## ADDED Requirements

### Requirement: Per-session sector and category performance breakdown

The system SHALL expose, on demand for a given paper-trading session, a breakdown of
the session's performance grouped both by the held assets' **sector** and by their
**category**. For each group the system SHALL report: the cumulative realised
profit/loss of positions closed in that group, the live unrealised profit/loss of the
session's open positions in that group (marked to market at request time), the total
profit/loss of the group (realised plus unrealised), the current market value of the
group's open positions, and the group's return as a fraction (the group's total
profit/loss divided by the group's invested cost basis). When a group's invested cost
basis is zero the return SHALL be reported as unavailable (no value) rather than
failing the request or dividing by zero.

Grouping SHALL be resolved by joining the session's open and closed positions to the
asset catalogue on a normalised ticker (matching the catalogue's canonical casing). An
asset whose sector is not set (for example crypto and most funds) SHALL be grouped
under a dedicated "no sector" bucket in the by-sector breakdown; its category is still
used for the by-category breakdown. A position whose ticker no longer matches any
catalogue asset SHALL be grouped under a dedicated "unknown" bucket in both
breakdowns, so the breakdown never silently drops profit/loss. Every unit of the
session's realised and unrealised profit/loss SHALL be attributed to exactly one group
in each breakdown. A request for an unknown session SHALL fail as not found.

#### Scenario: Breakdown grouped by sector and category

- **WHEN** a client requests the sector/category performance breakdown for an existing
  session
- **THEN** the system SHALL return two groupings — one keyed by sector and one keyed by
  category — each listing, per group, the realised P&L, unrealised P&L, total P&L,
  market value, and return fraction

#### Scenario: Total P&L combines realised and unrealised

- **WHEN** a group contains both closed positions and open positions
- **THEN** the group's total P&L SHALL equal its realised P&L (from closed positions)
  plus its unrealised P&L (from open positions marked to market at request time)

#### Scenario: Open positions marked to market

- **WHEN** the breakdown is computed for a session with open positions
- **THEN** each open position's unrealised P&L and market value SHALL be valued against
  current quotes at request time rather than a stale stored valuation

#### Scenario: Assets without a sector are bucketed

- **WHEN** the session holds or has closed an asset that has no sector (such as crypto)
- **THEN** that asset's performance SHALL be attributed to a dedicated "no sector"
  bucket in the by-sector breakdown while still being attributed to its own category in
  the by-category breakdown

#### Scenario: Unknown tickers are bucketed, not dropped

- **WHEN** a session position's ticker does not match any catalogue asset
- **THEN** that position's performance SHALL be attributed to a dedicated "unknown"
  bucket in both breakdowns rather than being omitted

#### Scenario: Group return guards divide-by-zero

- **WHEN** a group's invested cost basis is zero
- **THEN** the group's return SHALL be reported as unavailable rather than failing the
  request

#### Scenario: Unknown session

- **WHEN** a client requests the breakdown for a session id that does not exist
- **THEN** the system SHALL respond with a not-found error and no breakdown
