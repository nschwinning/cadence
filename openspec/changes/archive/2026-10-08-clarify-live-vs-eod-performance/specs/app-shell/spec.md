## MODIFIED Requirements

### Requirement: Session performance KPI tiles

The paper-trading session detail view SHALL present the session's live performance KPIs as headline tiles: current portfolio value, **unallocated (free) cash**, realised profit/loss, unrealised profit/loss, cumulative transaction fees, **daily average transaction cost**, total return, Sharpe ratio, benchmark return, and excess return over the benchmark. The total return tile SHALL show both the absolute money amount and the percentage. The unallocated-cash tile SHALL show the session's free cash as a money amount. The benchmark-return tile SHALL show the benchmark's return as a percentage and identify the benchmark. The excess-return tile SHALL show the session's return minus the benchmark's return as a percentage. Monetary profit/loss, the total return, and the excess return SHALL be visually distinguished by sign (gain versus loss / outperformance versus underperformance). The transaction-fees tile SHALL show the cumulative fees paid as a money amount. The daily-average-transaction-cost tile SHALL show the average transaction cost per snapshot day as a money amount, and SHALL display a clear "not yet available" state whenever the daily average transaction cost is unavailable because the session has no recorded daily value snapshots. The Sharpe tile SHALL display a clear "not yet available" state, with a brief explanatory hint, whenever the Sharpe ratio has not yet been computed because the session lacks sufficient history. The benchmark-return and excess-return tiles SHALL display a clear "not yet available" state whenever the benchmark figures are unavailable. The tiles SHALL reflect the values returned by the session KPI summary each time the view loads.

The performance KPI tiles section SHALL display a **live-data indicator** (for example, a "Live" badge beside the section heading) communicating that the tiles reflect current broker quotes as of when the summary was loaded, together with a brief explanatory hint that the figures are marked to market and can differ from the end-of-day value chart intraday. The indicator SHALL NOT change any tile value.

The headline performance tiles (current value, unallocated cash, realised P&L, unrealised P&L, transaction fees, daily average transaction cost, total return, Sharpe ratio, benchmark return, and excess return) SHALL be laid out as a compact grid of up to five tiles per row so the ten performance tiles occupy two rows on a wide viewport, and the KPI tiles SHALL use a reduced tile and font size relative to the prior layout while remaining legible and responsive on narrow viewports.

#### Scenario: KPIs shown on the session page

- **WHEN** a user opens a paper-trading session
- **THEN** the view SHALL display tiles for current portfolio value, unallocated cash, realised P&L, unrealised P&L, cumulative transaction fees, daily average transaction cost, total return, Sharpe ratio, benchmark return, and excess return using the session's live KPI summary

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

#### Scenario: Daily average transaction cost tile

- **WHEN** the session KPI summary reports a daily average transaction cost
- **THEN** the session detail view SHALL display a tile showing the average transaction cost per snapshot day as a money amount

#### Scenario: Daily average transaction cost not yet available

- **WHEN** the session KPI summary reports the daily average transaction cost as unavailable
- **THEN** the daily-average-transaction-cost tile SHALL show a "not yet available" state instead of a numeric value

### Requirement: Session value history chart

The paper-trading session view SHALL render a line chart of the session's total
portfolio value over time from its daily value-history snapshots, and SHALL overlay
on the same chart a second line for the session's benchmark — a buy-and-hold of the
session's allocated capital in the benchmark, rebased to start equal to the session's
value — so the two curves can be compared directly. When the benchmark value is
unavailable for the session's history, the view SHALL render the portfolio-value line
alone without error. When the session has fewer than two snapshots the view SHALL show
a placeholder indicating there is not yet enough history to chart, rather than a broken
or empty chart. While the value history is loading or fails to load, the view SHALL show
a loading or error state consistent with the page's other panels.

When the chart is rendered, it SHALL display a **labelled x-axis** marking calendar
dates across the plotted history and a **labelled y-axis** marking portfolio value in
USD, so a user can read what any point on a line represents. Axis tick labels SHALL be
rendered legibly (not distorted by the chart's scaling). The chart SHALL also show a
**legend** identifying which line is the session's portfolio value and which line is
the benchmark; when the benchmark line is not drawn, the legend SHALL not imply a
benchmark line is present.

The value history chart SHALL display an **end-of-day indicator** (for example, an "End
of day" badge beside the chart heading) communicating that the chart reflects end-of-day
value snapshots and that its latest point is the most recent snapshot (the prior close),
together with a brief explanatory hint that it can lag the live performance tiles
intraday. The indicator SHALL NOT change any plotted value.

#### Scenario: Chart renders with history

- **WHEN** a user opens a session that has at least two value snapshots
- **THEN** the view SHALL render a line chart of the session's total value over time

#### Scenario: Chart marked as end-of-day

- **WHEN** a user views the session value history chart
- **THEN** the view SHALL show an end-of-day indicator on the chart communicating that it reflects end-of-day snapshots, with a brief hint that it can lag the live performance tiles intraday

#### Scenario: Benchmark overlaid on the chart

- **WHEN** a user opens a session whose value history includes benchmark values
- **THEN** the view SHALL overlay the benchmark line on the value chart alongside the session's total-value line

#### Scenario: Benchmark unavailable

- **WHEN** a session's value history has no benchmark values
- **THEN** the view SHALL render the session's total-value line alone without error

#### Scenario: Axes are labelled

- **WHEN** the value chart is rendered with enough history to plot
- **THEN** the view SHALL show dated x-axis labels and USD y-axis labels around the plot area

#### Scenario: Legend identifies each line

- **WHEN** the value chart is rendered
- **THEN** the view SHALL show a legend naming the portfolio-value line and, when it is drawn, the benchmark line, each keyed to its line's colour or style

#### Scenario: Not enough history

- **WHEN** a user opens a session that has fewer than two value snapshots
- **THEN** the view SHALL show a placeholder indicating there is not yet enough
  history to chart

#### Scenario: Loading and error states

- **WHEN** the session's value history is loading or fails to load
- **THEN** the view SHALL show a loading or error state instead of the chart
