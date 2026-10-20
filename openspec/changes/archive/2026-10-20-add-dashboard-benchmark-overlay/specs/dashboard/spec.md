## ADDED Requirements

### Requirement: Benchmark price series in the overview

The range-scoped overview SHALL include, for each benchmark index in the fixed benchmark catalog, a price series over the selected range suitable for drawing a comparison line against the combined equity curve. Each series SHALL identify its benchmark by a stable identifier and a display name, and SHALL contain a sequence of points, each a date and that index's closing price on that date, windowed to the selected range on the same date basis as the per-session value series. A benchmark whose stored prices do not cover the range SHALL be represented as present in the catalog list but with an empty series rather than being omitted or causing an error. The series SHALL carry index prices only; it SHALL NOT be pre-rebased to any portfolio value, because rebasing depends on which sessions the client has selected.

#### Scenario: Benchmark series returned for the range

- **WHEN** a client requests the dashboard overview for a given range
- **THEN** the overview SHALL include, for each catalog benchmark, that index's identifier, display name, and a date/price series windowed to the selected range

#### Scenario: Benchmark with no prices over the range

- **WHEN** a catalog benchmark has no stored prices within the selected range
- **THEN** the overview SHALL still list that benchmark but with an empty price series, rather than omitting it or returning an error

#### Scenario: Empty system

- **WHEN** there are no active sessions and no assets
- **THEN** the overview SHALL return the benchmark catalog entries with empty price series rather than an error
