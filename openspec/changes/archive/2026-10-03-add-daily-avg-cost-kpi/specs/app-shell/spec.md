## MODIFIED Requirements

### Requirement: Session performance KPI tiles

The paper-trading session detail view SHALL present the session's live performance KPIs as headline tiles: current portfolio value, **unallocated (free) cash**, realised profit/loss, unrealised profit/loss, cumulative transaction fees, **daily average transaction cost**, total return, Sharpe ratio, benchmark return, and excess return over the benchmark. The total return tile SHALL show both the absolute money amount and the percentage. The unallocated-cash tile SHALL show the session's free cash as a money amount. The benchmark-return tile SHALL show the benchmark's return as a percentage and identify the benchmark. The excess-return tile SHALL show the session's return minus the benchmark's return as a percentage. Monetary profit/loss, the total return, and the excess return SHALL be visually distinguished by sign (gain versus loss / outperformance versus underperformance). The transaction-fees tile SHALL show the cumulative fees paid as a money amount. The daily-average-transaction-cost tile SHALL show the average transaction cost per snapshot day as a money amount, and SHALL display a clear "not yet available" state whenever the daily average transaction cost is unavailable because the session has no recorded daily value snapshots. The Sharpe tile SHALL display a clear "not yet available" state, with a brief explanatory hint, whenever the Sharpe ratio has not yet been computed because the session lacks sufficient history. The benchmark-return and excess-return tiles SHALL display a clear "not yet available" state whenever the benchmark figures are unavailable. The tiles SHALL reflect the values returned by the session KPI summary each time the view loads.

The headline performance tiles (current value, unallocated cash, realised P&L, unrealised P&L, transaction fees, daily average transaction cost, total return, Sharpe ratio, benchmark return, and excess return) SHALL be laid out as a compact grid of up to five tiles per row so the ten performance tiles occupy two rows on a wide viewport, and the KPI tiles SHALL use a reduced tile and font size relative to the prior layout while remaining legible and responsive on narrow viewports.

#### Scenario: KPIs shown on the session page

- **WHEN** a user opens a paper-trading session
- **THEN** the view SHALL display tiles for current portfolio value, unallocated cash, realised P&L, unrealised P&L, cumulative transaction fees, daily average transaction cost, total return, Sharpe ratio, benchmark return, and excess return using the session's live KPI summary

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

#### Scenario: Daily average transaction cost tile

- **WHEN** the session KPI summary reports a daily average transaction cost
- **THEN** the session detail view SHALL display a tile showing the average transaction cost per snapshot day as a money amount

#### Scenario: Daily average transaction cost not yet available

- **WHEN** the session KPI summary reports the daily average transaction cost as unavailable
- **THEN** the daily-average-transaction-cost tile SHALL show a "not yet available" state instead of a numeric value
