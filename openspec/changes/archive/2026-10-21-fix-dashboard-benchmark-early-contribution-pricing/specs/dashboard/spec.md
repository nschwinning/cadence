## MODIFIED Requirements

### Requirement: Benchmark price series in the overview

The range-scoped overview SHALL include, for each benchmark index in the fixed benchmark catalog, a price series over the selected range that a client uses to build a benchmark comparison line for the combined equity curve. Each series SHALL identify its benchmark by a stable identifier and a display name, and SHALL contain a sequence of points, each a date and that index's closing price on that date. The series SHALL be windowed to the plotted era on the same date basis as the per-session value series, except that its window SHALL extend back far enough to price the **earliest contribution across the active sessions**: the series SHALL include a closing price on or before the earliest session contribution's effective date, even when that date precedes the selected range window, so that **no** selected session's contribution is left unpriceable and dropped from the benchmark line. (A session's contributions comprise its opening capital at its first value-snapshot date plus any later capital increases, and are not windowed to the range.) The price series SHALL carry index prices only; it SHALL NOT be pre-converted to any portfolio-relative dollar value, because the dollar comparison line depends on which sessions the client has selected and on each session's capital contributions — the client combines the index prices with the selected sessions' contributions to produce a buy-and-hold dollar line that invests each session's contributed capital in that index at each contribution's effective date and holds. A benchmark whose stored prices do not cover the range SHALL be represented as present in the catalog list but with an empty series rather than being omitted or causing an error.

#### Scenario: Benchmark series returned for the range

- **WHEN** a client requests the dashboard overview for a given range
- **THEN** the overview SHALL include, for each catalog benchmark, that index's identifier, display name, and a date/price series covering the plotted era

#### Scenario: Session opened before the range start is still priceable

- **WHEN** a client requests the overview for a range whose start falls after some active session's opening date, so that session's opening contribution precedes the earliest range-windowed value point
- **THEN** each catalog benchmark's price series SHALL include a closing price on or before that session's earliest contribution date, so the client can price that contribution and count the session's capital in the benchmark line rather than dropping it

#### Scenario: Benchmark with no prices over the range

- **WHEN** a catalog benchmark has no stored prices within the plotted era
- **THEN** the overview SHALL still list that benchmark but with an empty price series, rather than omitting it or returning an error

#### Scenario: Empty system

- **WHEN** there are no active sessions and no assets
- **THEN** the overview SHALL return the benchmark catalog entries with empty price series rather than an error
