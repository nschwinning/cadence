## MODIFIED Requirements

### Requirement: Per-session performance data for the overview

For each active session the overview SHALL return the data needed to render aggregate performance, compare sessions, and compute per-session benchmark comparison lines over the selected range, without requiring the client to re-fetch when it changes which sessions are included. For each session this SHALL include a stable identifier, a display label, the allocated capital, the current value, the profit/loss and fees attributable to the selected range, a value series over the range suitable for plotting, and the session's capital contributions — the session's opening capital effective at its start date plus any later capital-increase events, each a contribution amount and the date it became effective. The value series SHALL be windowed to the selected range; a session that has no value before the range start SHALL be represented as contributing zero until its first recorded value.

#### Scenario: Session series windowed to the range

- **WHEN** the overview is requested for a range
- **THEN** each active session's returned value series SHALL cover the selected range and the session SHALL contribute zero for dates before its first recorded value

#### Scenario: Range-relative profit/loss and fees

- **WHEN** the overview is requested for a range
- **THEN** each session's returned profit/loss SHALL be its value at the end of the range minus its value at the start of the range, and its fees SHALL be those incurred within the range

#### Scenario: Session capital contributions included

- **WHEN** the overview is requested
- **THEN** each session's returned data SHALL include its capital contributions — its opening capital with the date it became effective and any later capital-increase amounts each with their effective date — so a client can compute a buy-and-hold benchmark comparison for that session

### Requirement: Benchmark price series in the overview

The range-scoped overview SHALL include, for each benchmark index in the fixed benchmark catalog, a price series over the selected range that a client uses to build a benchmark comparison line for the combined equity curve. Each series SHALL identify its benchmark by a stable identifier and a display name, and SHALL contain a sequence of points, each a date and that index's closing price on that date, windowed to the selected range on the same date basis as the per-session value series. The price series SHALL carry index prices only; it SHALL NOT be pre-converted to any portfolio-relative dollar value, because the dollar comparison line depends on which sessions the client has selected and on each session's capital contributions — the client combines the index prices with the selected sessions' contributions to produce a buy-and-hold dollar line that invests each session's contributed capital in that index at each contribution's effective date and holds. A benchmark whose stored prices do not cover the range SHALL be represented as present in the catalog list but with an empty series rather than being omitted or causing an error.

#### Scenario: Benchmark series returned for the range

- **WHEN** a client requests the dashboard overview for a given range
- **THEN** the overview SHALL include, for each catalog benchmark, that index's identifier, display name, and a date/price series windowed to the selected range

#### Scenario: Benchmark with no prices over the range

- **WHEN** a catalog benchmark has no stored prices within the selected range
- **THEN** the overview SHALL still list that benchmark but with an empty price series, rather than omitting it or returning an error

#### Scenario: Empty system

- **WHEN** there are no active sessions and no assets
- **THEN** the overview SHALL return the benchmark catalog entries with empty price series rather than an error
