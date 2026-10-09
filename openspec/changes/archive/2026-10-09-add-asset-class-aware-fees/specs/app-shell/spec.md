## REMOVED Requirements

### Requirement: Session performance KPI tiles

## ADDED Requirements

### Requirement: Session performance KPI tile grid

The paper-trading session detail view SHALL present the session's live performance KPIs as headline tiles: current portfolio value, **unallocated (free) cash**, realised profit/loss, unrealised profit/loss, cumulative transaction fees, **daily average orders**, total return, Sharpe ratio, benchmark return, and excess return over the benchmark. The total return tile SHALL show both the absolute money amount and the percentage. The unallocated-cash tile SHALL show the session's free cash as a money amount. The benchmark-return tile SHALL show the benchmark's return as a percentage and identify the benchmark. The excess-return tile SHALL show the session's return minus the benchmark's return as a percentage. Monetary profit/loss, the total return, and the excess return SHALL be visually distinguished by sign (gain versus loss / outperformance versus underperformance). The transaction-fees tile SHALL show the cumulative fees paid as a money amount. The daily-average-orders tile SHALL show the session's average number of filled orders per snapshot day as a number, and SHALL display a clear "not yet available" state whenever the daily average orders is unavailable because the session has no recorded daily value snapshots. The Sharpe tile SHALL display a clear "not yet available" state, with a brief explanatory hint, whenever the Sharpe ratio has not yet been computed because the session lacks sufficient history. The benchmark-return and excess-return tiles SHALL display a clear "not yet available" state whenever the benchmark figures are unavailable. The tiles SHALL reflect the values returned by the session KPI summary each time the view loads.

The performance KPI tiles section SHALL display a **live-data indicator** (for example, a "Live" badge beside the section heading) communicating that the tiles reflect current broker quotes as of when the summary was loaded, together with a brief explanatory hint that the figures are marked to market and can differ from the end-of-day value chart intraday. The indicator SHALL NOT change any tile value.

The headline performance tiles (current value, unallocated cash, realised P&L, unrealised P&L, transaction fees, daily average orders, total return, Sharpe ratio, benchmark return, and excess return) SHALL be laid out as a compact grid of up to five tiles per row so the ten performance tiles occupy two rows on a wide viewport, and the KPI tiles SHALL use a reduced tile and font size relative to the prior layout while remaining legible and responsive on narrow viewports.

#### Scenario: KPIs shown on the session page

- **WHEN** a user opens a paper-trading session
- **THEN** the view SHALL display tiles for current portfolio value, unallocated cash, realised P&L, unrealised P&L, cumulative transaction fees, daily average orders, total return, Sharpe ratio, benchmark return, and excess return using the session's live KPI summary

#### Scenario: Performance tiles marked as live

- **WHEN** a user views the session performance KPI tiles
- **THEN** the view SHALL show a live-data indicator on the tiles section communicating that the figures reflect current broker quotes, with a brief hint that they can differ from the end-of-day value chart intraday

#### Scenario: Performance tiles laid out as two compact rows

- **WHEN** a user views the session performance KPI tiles on a wide viewport
- **THEN** the ten performance tiles SHALL be arranged as a compact grid of up to five tiles per row (two rows) with a reduced tile and font size

#### Scenario: Unallocated cash tile

- **WHEN** the session KPI summary reports the session's unallocated cash
- **THEN** the view SHALL display an unallocated-cash tile showing the free cash as a money amount

#### Scenario: Total return shows amount and percentage

- **WHEN** the session KPI summary is displayed
- **THEN** the total return tile SHALL show the absolute money amount together with the percentage of allocated capital

#### Scenario: Benchmark and excess return shown

- **WHEN** the session KPI summary reports a benchmark return and excess return
- **THEN** the view SHALL display a benchmark-return tile (identifying the benchmark) and an excess-return tile as percentages

#### Scenario: Benchmark not yet available

- **WHEN** the session KPI summary reports the benchmark return and excess return as unavailable
- **THEN** the benchmark-return and excess-return tiles SHALL show a "not yet available" state instead of numeric values

#### Scenario: Gains and losses distinguished

- **WHEN** a session's realised P&L, unrealised P&L, total return, or excess return is positive or negative
- **THEN** the corresponding tile SHALL indicate the sign visually (gain versus loss)

#### Scenario: Sharpe not yet available

- **WHEN** the session KPI summary reports the Sharpe ratio as unavailable
- **THEN** the Sharpe tile SHALL show a "not yet available" state with a brief hint instead of a numeric value

#### Scenario: Transaction fees tile

- **WHEN** a session has accrued transaction fees
- **THEN** the session detail view SHALL display a tile showing the cumulative transaction fees as a money amount

#### Scenario: Daily average orders tile

- **WHEN** the session KPI summary reports a daily average orders value
- **THEN** the session detail view SHALL display a tile showing the session's average number of filled orders per snapshot day as a number

#### Scenario: Daily average orders not yet available

- **WHEN** the session KPI summary reports the daily average orders as unavailable
- **THEN** the daily-average-orders tile SHALL show a "not yet available" state instead of a numeric value
