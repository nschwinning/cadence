# app-shell Specification

## Purpose
Provides the web application's persistent shell and navigation so users can move between the dashboard, assets, portfolios, and paper-trading views, and interact with asynchronous AI runs through a consistent, responsive interface.

## Requirements

### Requirement: Persistent application shell

The system SHALL present a persistent shell (header and sidebar navigation with the main content area) around every page. Navigation SHALL offer entries for Dashboard, Assets, Portfolios, Paper Trading, Runs, and System, and SHALL indicate the active view. The shell SHALL be responsive, collapsing the sidebar on small viewports.

#### Scenario: Navigate between views

- **WHEN** a user selects a navigation entry
- **THEN** the application SHALL render that view within the shell and mark the entry active without a full page reload

#### Scenario: Small viewport

- **WHEN** the viewport is narrow
- **THEN** the sidebar SHALL collapse into a toggleable menu

### Requirement: Asset management views

The system SHALL provide a view to add an asset, browse the paginated/searchable/filterable asset list, and open an asset's detail (including its recent price history and profile). Errors from the API (duplicate, unknown ticker, data unavailable) SHALL be surfaced to the user with a meaningful message.

#### Scenario: Add and browse assets

- **WHEN** a user adds a ticker and browses the list
- **THEN** the newly added asset SHALL appear in the list and be openable in a detail view

#### Scenario: Add error surfaced

- **WHEN** adding a ticker returns a duplicate/unknown/unavailable error
- **THEN** the UI SHALL display a corresponding message and remain usable

### Requirement: AI run views with polling

The system SHALL let a user start asynchronous AI runs (recommendations, portfolio build, rebalance) and SHALL poll their status until a terminal state, reflecting progress and final outcome in the UI without manual refresh.

#### Scenario: Start and follow a run

- **WHEN** a user starts an AI recommendation, build, or rebalance
- **THEN** the UI SHALL show it as in-progress and SHALL automatically update to the final result when the run reaches a terminal state

### Requirement: Portfolio and paper-trading views

The system SHALL provide views to list portfolios and open a portfolio, and to list paper-trading sessions and open a session showing its trades, runs, positions, and AI-portfolio events. The session list and the session detail header SHALL identify each session by its portfolio name as the primary label, and SHALL present the strategy as secondary context rather than the primary identifier. When a session has no resolvable portfolio name, the UI SHALL fall back to the strategy label. The session detail view SHALL display the session's **automatic stop-loss configuration** — whether it is enabled and, when enabled, its threshold percentage. The session detail view SHALL display the session's **risk-guardrail configuration** — whether the guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage. Among the session's trades and runs, those produced by the automatic stop-loss SHALL be identifiable as stop-loss activity (rather than AI-driven build or rebalance activity). On the session detail view, a run that was produced by an AI build or rebalance SHALL link to that run's detail view; a run not backed by an AI-portfolio event SHALL remain non-interactive.

On the session detail view, each of the four tables — AI-portfolio events, trades, closed positions, and runs — SHALL show one fixed-size page of rows at a time rather than a single unbounded list, with the first page showing the most recent rows. The default page size SHALL be 5 rows for the AI-portfolio events and runs tables and 10 rows for the trades and closed-positions tables. Each table SHALL provide page-through navigation (moving to the previous and next page, without infinite scroll) and SHALL indicate the user's position within the whole (for example, the current page relative to the total number of pages or rows). When a table has no more than one page of rows, its navigation SHALL convey that there are no further pages. Paging one table SHALL NOT change the page shown by the other tables.

#### Scenario: Inspect a paper-trading session

- **WHEN** a user opens a paper-trading session
- **THEN** the UI SHALL display its trades, runs, positions, and the AI decision events for that session

#### Scenario: Sessions are labeled by portfolio

- **WHEN** a user views the paper-trading session list or a session's detail header
- **THEN** the UI SHALL show the portfolio name as the primary label and the strategy as secondary context

#### Scenario: Fallback when portfolio name is missing

- **WHEN** a session has no resolvable portfolio name
- **THEN** the UI SHALL show the strategy label in place of the portfolio name

#### Scenario: Session shows its stop-loss configuration

- **WHEN** a user opens a session's detail view
- **THEN** the UI SHALL display whether the automatic stop-loss is enabled and, when enabled, its threshold percentage

#### Scenario: Session shows its guardrail configuration

- **WHEN** a user opens a session's detail view for a session built with the risk guardrails enabled
- **THEN** the UI SHALL display that the guardrails are enabled together with the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage

#### Scenario: Session shows guardrails disabled

- **WHEN** a user opens a session's detail view for a session built without the risk guardrails
- **THEN** the UI SHALL indicate that the risk guardrails are disabled

#### Scenario: Stop-loss activity is identifiable

- **WHEN** a user views the trades and runs of a session that has been stopped out at least once
- **THEN** the UI SHALL identify the stop-loss sale trades and stop-loss runs as stop-loss activity, distinct from AI build or rebalance activity

#### Scenario: AI-driven run links to its detail view

- **WHEN** a user views the runs table of a session and a run was produced by an AI build or rebalance
- **THEN** the UI SHALL present that run row as a link that opens the run's detail view

#### Scenario: Non-AI run is not linked

- **WHEN** a user views the runs table of a session and a run was not produced by an AI build or rebalance (for example an automatic stop-loss run)
- **THEN** the UI SHALL present that run row as non-interactive text with no link

#### Scenario: Tables show one page at a time

- **WHEN** a user opens a session whose events, trades, closed positions, or runs exceed the table's default page size
- **THEN** the UI SHALL show only the first page of the most recent rows for that table — 5 rows for events and runs, 10 rows for trades and closed positions — with page-through controls to reach the remaining rows

#### Scenario: Browsing pages of a table

- **WHEN** a user advances to the next or previous page of one of the four tables
- **THEN** the UI SHALL load and display that page's rows for that table and update the indicator of the user's position within the total, while leaving the other tables on their current page

#### Scenario: Single-page table

- **WHEN** a table has no more than one page of rows
- **THEN** the UI SHALL indicate there are no further pages to browse

### Requirement: AI run history and detail views

The system SHALL provide a Runs view that lists AI runs (build and rebalance) across all sessions, newest first, showing at least each run's type, status, number of orders executed, and time, and SHALL let a user open a run to a detail view. The run detail view SHALL show the run's AI reasoning, its research (each web search's query and results), the trades the run opened, the positions the run closed, and — when the run recorded trend-decision context — the technical-indicator picture behind the run: the candidates that were filtered out by the trend gate (each with the reason it failed) and the indicator annotations that were handed to the AI for the surviving candidates and for the current holdings (including the holdings' reversal flags). When a run recorded no trend-decision context, the detail view SHALL simply omit that section rather than show an error.

#### Scenario: Browse runs

- **WHEN** a user opens the Runs view
- **THEN** the UI SHALL list AI runs across all sessions newest first and allow opening any run's detail

#### Scenario: Inspect a run

- **WHEN** a user opens a run's detail
- **THEN** the UI SHALL display the run's reasoning, its research (queries and results), the trades it opened, and the positions it closed

#### Scenario: Inspect a run's trend-decision context

- **WHEN** a user opens the detail of a run that recorded trend-decision context
- **THEN** the UI SHALL display the candidates filtered out by the trend gate with their reasons and the indicator annotations handed to the AI for the surviving candidates and the holdings (with reversal flags)

#### Scenario: Run without trend-decision context

- **WHEN** a user opens the detail of a run that recorded no trend-decision context
- **THEN** the UI SHALL omit the trend-decision section without error

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

#### Scenario: Chart renders with history

- **WHEN** a user opens a session that has at least two value snapshots
- **THEN** the view SHALL render a line chart of the session's total value over time

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

### Requirement: Archive controls for sessions and portfolios

The UI SHALL let a user archive and unarchive paper-trading sessions and portfolios.
The session list, the session detail view, and the portfolio list SHALL each offer an
archive action for eligible items and an unarchive action for archived items. The
session archive action SHALL be available only for a stopped session. Archived items
SHALL be hidden from the default session and portfolio lists, and each list SHALL
provide a "Show archived" toggle that reveals archived items and visibly marks them as
archived. After archiving or unarchiving, the affected list SHALL reflect the change
without requiring a manual page reload.

#### Scenario: Archive a stopped session from the UI

- **WHEN** a user invokes the archive action on a stopped session
- **THEN** the UI SHALL archive the session and remove it from the default session
  list

#### Scenario: Show and unarchive archived items

- **WHEN** a user enables the "Show archived" toggle on the session or portfolio list
- **THEN** the UI SHALL display archived items marked as archived and SHALL offer an
  unarchive action that restores an item to the default list

#### Scenario: Archive action limited to eligible items

- **WHEN** a user views a session that is active or paused, or a portfolio that has an
  active or paused session
- **THEN** the UI SHALL NOT offer an enabled archive action for that item

### Requirement: Session detail syncs order state until terminal

When a user opens a paper-trading session's detail view, the UI SHALL request a
reconciliation of that session's order state so that displayed order statuses reflect
the latest broker information rather than only what was known at submission. While any
of the session's orders is in a non-terminal status, the UI SHALL keep refreshing the
session's order state on a recurring interval, and it SHALL stop refreshing once every
order has reached a terminal status. Reconciled statuses, fill prices, and updated
position values SHALL become visible without requiring a manual page reload.

#### Scenario: Reconcile on opening the session detail view

- **WHEN** a user opens a session's detail view
- **THEN** the UI SHALL request reconciliation of that session's orders and SHALL
  display the resulting order statuses and fills

#### Scenario: Poll while orders are non-terminal

- **WHEN** the session's detail view is open and at least one order is in a
  non-terminal status
- **THEN** the UI SHALL continue refreshing the session's order state on a recurring
  interval and reflect updates without a manual reload

#### Scenario: Stop polling once all orders are terminal

- **WHEN** every order in the open session has reached a terminal status
- **THEN** the UI SHALL stop the recurring refresh

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

### Requirement: AI build form asset scope and default capital

The AI portfolio build form SHALL let the user choose the portfolio's asset scope — stocks only, crypto only, or both — defaulting to both, and SHALL let the user choose the session's benchmark from the fixed benchmark catalog, defaulting to S&P 500. The form SHALL also let the user opt the portfolio into the **technical-indicator trend strategy** via a toggle that defaults to **off**. The form SHALL also let the user opt the portfolio into an **automatic hard stop-loss** via a toggle that defaults to **off**, and SHALL let the user set the **stop-loss threshold percentage** (defaulting to the configured default) that applies when the stop-loss is enabled; the threshold control MAY be hidden or disabled while the stop-loss toggle is off. The form SHALL also let the user opt the portfolio into **portfolio risk guardrails** via a toggle that defaults to **off**, and SHALL let the user set the guardrail parameters that apply when the guardrails are enabled — the **maximum percentage per asset**, the **maximum percentage per asset class**, the **minimum number of positions**, and the **maximum invested percentage** (cash buffer) — each defaulting to its configured default; the guardrail parameter controls MAY be hidden or disabled while the guardrail toggle is off. The form's allocated-capital input SHALL default to the configured default amount (10,000). The chosen asset scope SHALL be sent with the build request so the resulting portfolio is restricted to the selected asset types, the chosen benchmark SHALL be sent with the build request so the session is compared against it, the technical-indicator opt-in SHALL be sent with the build request so the resulting session applies (or omits) the trend strategy accordingly, the stop-loss opt-in and (when enabled) threshold SHALL be sent with the build request so the resulting session applies (or omits) the automatic stop-loss accordingly, and the risk-guardrail opt-in and (when enabled) its parameters SHALL be sent with the build request so the resulting session applies (or omits) the guardrails accordingly.

#### Scenario: Default form values

- **WHEN** a user opens the AI portfolio build form
- **THEN** the capital input SHALL default to 10,000, the asset scope SHALL default to both (stocks and crypto), the benchmark SHALL default to S&P 500, the technical-indicator trend-strategy toggle SHALL default to off, the automatic stop-loss toggle SHALL default to off, and the risk-guardrails toggle SHALL default to off

#### Scenario: Selecting an asset scope

- **WHEN** a user selects stocks only (or crypto only) and submits the build form
- **THEN** the UI SHALL send the selected asset scope with the build request

#### Scenario: Selecting a benchmark

- **WHEN** a user selects a benchmark from the catalog and submits the build form
- **THEN** the UI SHALL send the selected benchmark with the build request

#### Scenario: Opting into the technical-indicator trend strategy

- **WHEN** a user enables the technical-indicator trend-strategy toggle and submits the build form
- **THEN** the UI SHALL send the technical-indicator opt-in with the build request so the resulting session applies the trend strategy

#### Scenario: Leaving the trend strategy off

- **WHEN** a user submits the build form without enabling the technical-indicator toggle
- **THEN** the UI SHALL send the build request with the opt-in off so the resulting session does not apply the trend strategy

#### Scenario: Opting into the automatic stop-loss

- **WHEN** a user enables the automatic stop-loss toggle, sets a threshold percentage, and submits the build form
- **THEN** the UI SHALL send the stop-loss opt-in and the chosen threshold with the build request so the resulting session applies the automatic stop-loss

#### Scenario: Leaving the stop-loss off

- **WHEN** a user submits the build form without enabling the automatic stop-loss toggle
- **THEN** the UI SHALL send the build request with the stop-loss off so the resulting session does not apply an automatic stop-loss

#### Scenario: Opting into the risk guardrails

- **WHEN** a user enables the risk-guardrails toggle, sets the maximum-per-asset, maximum-per-class, minimum-positions, and maximum-invested values, and submits the build form
- **THEN** the UI SHALL send the guardrail opt-in and the chosen parameters with the build request so the resulting session applies the guardrails

#### Scenario: Leaving the guardrails off

- **WHEN** a user submits the build form without enabling the risk-guardrails toggle
- **THEN** the UI SHALL send the build request with the guardrails off so the resulting session applies no allocation caps

### Requirement: Switch a session's benchmark from the detail view

The paper-trading session detail view SHALL let the user change the session's benchmark to any benchmark in the fixed catalog at any time, presenting the available benchmarks for selection with the session's current benchmark shown as selected. On confirming a change, the UI SHALL request the change and, on success, refresh the session's benchmark-dependent figures (value-history benchmark line and benchmark/excess-return KPI tiles) to reflect the new benchmark. While the change is in flight the control SHALL indicate progress, and a failed change SHALL surface an error without leaving the view in an inconsistent state.

#### Scenario: Change the benchmark from the detail view

- **WHEN** a user selects a different benchmark on the session detail view and confirms
- **THEN** the UI SHALL request the change and, on success, refresh the chart benchmark line and the benchmark and excess-return tiles to the new benchmark

#### Scenario: Current benchmark preselected

- **WHEN** a user opens the benchmark control on the session detail view
- **THEN** the control SHALL present the catalog benchmarks with the session's current benchmark selected

#### Scenario: Failed change surfaces an error

- **WHEN** a benchmark change request fails
- **THEN** the UI SHALL surface an error and leave the session's displayed benchmark unchanged

### Requirement: Show and switch a session's asset scope from the detail view

The paper-trading session detail view SHALL display the session's current asset scope (stocks, crypto, or both) as a labeled fact alongside the session's other configuration facts. The detail view SHALL let the user change the session's scope to any supported scope at any time, presenting the available scopes for selection with the session's current scope shown as selected. When the selected scope change would liquidate currently-held positions — a narrowing that excludes the asset class of one or more open positions — the UI SHALL warn the user that those holdings will be sold and SHALL require the user to explicitly confirm before the change is requested; if the user does not confirm, no change SHALL be requested and the session's displayed scope SHALL remain unchanged. A scope change that would liquidate nothing (a widening, or a narrowing that excludes no held position) SHALL NOT require such a warning. On confirming a change, the UI SHALL request the change and, on success, refresh the session's scope-dependent figures (at least the displayed scope and the session's value and KPI figures, which a narrowing liquidation can move). While the change is in flight the control SHALL indicate progress, and a failed change SHALL surface an error without leaving the view in an inconsistent state.

#### Scenario: Scope shown on the detail view

- **WHEN** a user opens a paper-trading session's detail view
- **THEN** the view SHALL display the session's current asset scope (stocks, crypto, or both)

#### Scenario: Change the scope from the detail view

- **WHEN** a user selects a different scope on the session detail view and confirms
- **THEN** the UI SHALL request the change and, on success, refresh the displayed scope and the session's value/KPI figures

#### Scenario: Warn and confirm before a narrowing that liquidates holdings

- **WHEN** a user selects a scope change that would sell one or more currently-held positions whose asset class the new scope excludes
- **THEN** the UI SHALL warn the user that those holdings will be liquidated and SHALL request the change only after the user explicitly confirms

#### Scenario: Declining the warning cancels the change

- **WHEN** the UI warns about a liquidating scope change and the user does not confirm
- **THEN** the UI SHALL NOT request the change and the session's displayed scope SHALL remain unchanged

#### Scenario: Non-liquidating change needs no warning

- **WHEN** a user selects a scope change that would sell no currently-held position (a widening, or a narrowing that excludes nothing held)
- **THEN** the UI SHALL request the change without requiring a liquidation warning

#### Scenario: Current scope preselected

- **WHEN** a user opens the scope control on the session detail view
- **THEN** the control SHALL present the supported scopes with the session's current scope selected

#### Scenario: Failed change surfaces an error

- **WHEN** a scope change request fails
- **THEN** the UI SHALL surface an error and leave the session's displayed scope unchanged

### Requirement: Monetary values displayed in USD

The application SHALL display monetary values in US dollars (`$`), consistent with the brokerage's settlement currency, across all views (including capital amounts, P&L figures, portfolio value, and KPI tiles).

#### Scenario: Money rendered as USD

- **WHEN** the UI displays a monetary amount
- **THEN** it SHALL be formatted as US dollars with a `$` symbol rather than another currency

### Requirement: Paper-trading session comparison chart

The paper-trading session list view SHALL display a **performance-comparison chart** that overlays every non-archived session (active, paused, stopped) on a shared time axis, so a user can compare sessions and see which performs best. The chart SHALL plot one line per session that has at least two value points, sharing a single y-scale across all plotted lines, and SHALL show a **legend** mapping each line's color to its session label. Sessions with fewer than two value points SHALL appear in the legend but SHALL NOT be plotted. The chart SHALL offer a **metric toggle** with two views, defaulting to the return view:

- **Return %** (default): each session's line SHALL be its cumulative total-return percentage, computed from the session's total value relative to its allocated capital, so sessions with different allocated capital and start dates are compared fairly and the highest line is the best performer.
- **Value ($)**: each session's line SHALL be its absolute total portfolio value in USD.

When the chart plots at least one line, it SHALL display a **labelled x-axis** marking calendar dates across the shared time axis and a **labelled y-axis** whose tick labels match the active metric — percentages in the Return % view and USD amounts in the Value $ view — and the y-axis labels SHALL update when the metric toggle switches. Axis tick labels SHALL be rendered legibly (not distorted by the chart's scaling).

When no non-archived session has enough value points to plot, the chart SHALL show an insufficient-data placeholder rather than an empty plot area. The chart SHALL show its own loading and error states while the comparison data is being fetched or if the fetch fails. The existing single-session value chart on the session detail view SHALL remain unchanged.

#### Scenario: Comparison chart overlays non-archived sessions

- **WHEN** a user opens the paper-trading session list and multiple non-archived sessions each have at least two value points
- **THEN** the chart SHALL render one line per such session on a shared y-scale with a legend identifying each session by its label

#### Scenario: Toggle between return % and absolute value

- **WHEN** a user switches the metric toggle from the default return view to the value view
- **THEN** the chart SHALL re-plot each session's line as its absolute portfolio value in USD, and switching back SHALL re-plot cumulative total-return percentage

#### Scenario: Return view is the default

- **WHEN** the comparison chart first renders
- **THEN** it SHALL show the cumulative total-return percentage view by default

#### Scenario: Axes are labelled and track the metric

- **WHEN** the comparison chart plots at least one line
- **THEN** the view SHALL show dated x-axis labels and y-axis labels formatted as percentages in the Return % view and as USD amounts in the Value $ view, and the y-axis labels SHALL change when the metric toggle is switched

#### Scenario: Session with too little history is legended but not plotted

- **WHEN** a non-archived session has fewer than two value points
- **THEN** that session SHALL appear in the legend but SHALL NOT be drawn as a line

#### Scenario: Insufficient data placeholder

- **WHEN** no non-archived session has at least two value points
- **THEN** the chart SHALL display an insufficient-data placeholder instead of an empty plot

#### Scenario: Loading and error states

- **WHEN** the comparison data is loading, or the request fails
- **THEN** the chart SHALL show a loading indicator while pending and an error state on failure, rather than a blank or broken chart

### Requirement: Session-detail drawdown and trade-effectiveness KPI tiles

The paper-trading session-detail page SHALL display KPI tiles for the session's maximum drawdown, win rate, average win, average loss, best trade, and worst trade, alongside the existing session KPI tiles. Each tile SHALL render its metric using the value from the session KPI read, formatting maximum drawdown and win rate as percentages and the average/best/worst trade figures as currency amounts. When a metric is reported as absent, its tile SHALL render a neutral placeholder rather than a misleading numeric value. These tiles SHALL appear on the session-detail page only and SHALL NOT be added to the multi-session comparison list.

#### Scenario: Tiles show the new metrics

- **WHEN** a user views the detail page for a session whose KPI read returns maximum drawdown, win rate, and trade-effectiveness figures
- **THEN** the page SHALL display tiles for maximum drawdown and win rate as percentages and for average win, average loss, best trade, and worst trade as currency amounts

#### Scenario: Absent metric shows a placeholder

- **WHEN** a user views the detail page for a session whose KPI read reports one or more of these metrics as absent
- **THEN** each affected tile SHALL display a neutral placeholder instead of a numeric value

### Requirement: Asset-composition donut charts

The Assets page SHALL present the asset universe's composition by category and by sector each as a donut (ring) chart. Each chart SHALL render one slice per breakdown entry, with the slice's angular size proportional to that entry's share of the breakdown's total count, and SHALL display the breakdown's total count at its center. The two charts SHALL be rendered as equal-sized tiles.

Slice identity SHALL be revealed on hover or keyboard focus rather than through a persistent legend: hovering or focusing a slice SHALL reveal that entry's human-readable label, its exact count, and its percentage of the breakdown's total. The percentage SHALL be computed on the client from the counts; the charts SHALL NOT require any new data from the metrics endpoint.

When a breakdown has no entries, the page SHALL show an empty-state message in place of the chart rather than an empty or broken chart.

The Dashboard SHALL NOT render these asset-composition donut charts.

#### Scenario: Composition shown as equal-sized donut charts on the Assets page

- **WHEN** a user opens the Assets page and the asset universe has categorized and sectored assets
- **THEN** the UI SHALL render the by-category and by-sector breakdowns each as a donut chart whose slices are sized by each entry's share of the total, with the total count shown at the center, and the two charts SHALL be equal-sized tiles

#### Scenario: Slice hover reveals exact value and percentage

- **WHEN** a user hovers or focuses a slice of a breakdown donut chart
- **THEN** the UI SHALL show that entry's human-readable label, its exact count, and its percentage of the breakdown's total

#### Scenario: No persistent legend

- **WHEN** a breakdown donut chart is displayed
- **THEN** the chart SHALL NOT render a persistent list mapping each slice's color to its label; slice identity is available only on hover or keyboard focus

#### Scenario: Percentages sum across the breakdown

- **WHEN** a breakdown donut chart is displayed
- **THEN** each slice's percentage SHALL be that entry's count divided by the sum of all entries' counts in the breakdown, derived on the client without additional data from the metrics endpoint

#### Scenario: Empty breakdown

- **WHEN** a breakdown has no entries
- **THEN** the UI SHALL show an empty-state message instead of a donut chart

#### Scenario: Dashboard no longer shows the donut charts

- **WHEN** a user opens the Dashboard
- **THEN** the asset-composition donut charts SHALL NOT appear there

### Requirement: Dashboard global range selector

The Dashboard SHALL present a single range selector offering the choices `1D`, `1W`, `1M`, `YTD`, `1Y`, and `Max`, with one range active at a time. Changing the selected range SHALL drive every range-dependent section of the Dashboard (performance tiles, equity curve, portfolio leaderboard, automation failed-run count, recent activity, and universe performers) so that the whole view answers for the same horizon. The universe balance summary is range-independent and SHALL NOT change with the selector.

#### Scenario: Selecting a range updates the whole dashboard

- **WHEN** a user selects a different range
- **THEN** the performance tiles, equity curve, leaderboard, recent activity, and universe performers SHALL all refresh to that range while the universe balance summary stays unchanged

### Requirement: Dashboard aggregate performance tiles

The Dashboard SHALL present hero performance tiles aggregated over the active sessions currently selected in the equity curve: total current value, profit/loss over the selected range, money-weighted return over the selected range, and fees incurred within the range. The tiles SHALL reflect the current portfolio selection and the selected range.

#### Scenario: Tiles reflect range and selection

- **WHEN** a user changes the range or the set of selected portfolios
- **THEN** the hero tiles SHALL recompute to show aggregate value, range profit/loss, money-weighted range return, and range fees for the selected sessions

### Requirement: Dashboard combined equity curve

The Dashboard SHALL present a combined equity curve as a single line equal to the summed value of the selected active sessions over the selected range, on a common date axis. A session SHALL contribute zero before its first recorded value (carry-forward thereafter). The Dashboard SHALL offer a selectable list of the active sessions, all selected by default, letting the user include or exclude each session; the selection SHALL also drive the hero tiles and the leaderboard. Toggling a session SHALL re-aggregate from already-fetched per-session data without issuing a new request per toggle. When no session is selected, the chart SHALL show an empty state instead of a line.

#### Scenario: Summed line over selected sessions

- **WHEN** the Dashboard renders the equity curve with one or more sessions selected
- **THEN** it SHALL plot a single line equal to the sum of the selected sessions' values across the range, each session contributing zero before its first recorded value

#### Scenario: Toggling a session re-aggregates without refetch

- **WHEN** a user includes or excludes a session in the equity curve
- **THEN** the line, hero tiles, and leaderboard SHALL recompute from already-fetched data without a new request per toggle

#### Scenario: No sessions selected

- **WHEN** no session is selected
- **THEN** the equity curve SHALL show an empty state rather than a line

### Requirement: Dashboard portfolio leaderboard

The Dashboard SHALL present a leaderboard table of the selected active sessions, sorted by return over the selected range in descending order (best first). Each row SHALL show the portfolio's name, current value, range profit/loss, range return, and range fees, using the same money-weighted basis as the hero tiles, and SHALL link to that session's detail view. Return direction SHALL be visually distinguished (for example gains and losses colored differently). Deselecting a session in the equity curve SHALL remove it from the leaderboard.

#### Scenario: Sessions ranked by range return

- **WHEN** the Dashboard renders the leaderboard for a range
- **THEN** it SHALL list the selected sessions sorted by range return descending, each row showing name, value, range profit/loss, range return, and range fees, and linking to that session's detail view

#### Scenario: Selection narrows the leaderboard

- **WHEN** a user deselects a session
- **THEN** that session SHALL no longer appear in the leaderboard

### Requirement: Dashboard automation panel

The Dashboard SHALL present an automation panel showing the latest rebalance run's status and relative time with a link to that run, an indicator when a run is currently in flight, the count of failed runs within the selected range, and the approximate next scheduled run. The next run SHALL be labeled as approximate.

#### Scenario: Automation health shown

- **WHEN** the Dashboard renders the automation panel
- **THEN** it SHALL show the latest rebalance run (status, relative time, link), an in-flight indicator when applicable, the failed-run count within the range, and an approximate next-run time

### Requirement: Dashboard recent activity feed

The Dashboard SHALL present a recent-activity feed listing AI runs (build, rebalance, close) across sessions within the selected range, newest first and capped at a maximum count. Each entry SHALL show its kind, status, session label, relative time, and a link to that run.

#### Scenario: Recent activity listed

- **WHEN** the Dashboard renders the recent-activity feed for a range
- **THEN** it SHALL list the most recent AI runs within that range, newest first and capped, each showing kind, status, session label, relative time, and a link to the run

### Requirement: Dashboard universe section

The Dashboard SHALL present a universe section with a range-independent balance summary and range-dependent performers. The balance summary SHALL show the eligible versus ineligible split, the number of sectors represented, the largest sector's share, and the largest category's share. The performers SHALL show the best and worst tracked assets by market return over the selected range.

#### Scenario: Balance summary and performers shown

- **WHEN** the Dashboard renders the universe section
- **THEN** it SHALL show the current eligibility split, sectors represented, and largest sector and category shares, alongside the best and worst tracked assets by market return over the selected range

#### Scenario: Performers follow the range

- **WHEN** a user changes the selected range
- **THEN** the best/worst performers SHALL update to that range while the balance summary stays unchanged

### Requirement: Technical Indicators navigation entry and info page

The application shell SHALL offer a top-level "Technical Indicators" navigation entry that opens a dedicated page, and SHALL mark it active when that page is shown, consistent with the shell's other navigation entries. The page SHALL present the configured technical-indicator setup as read-only information obtained from the backend configuration — not editable and not per-asset. It SHALL display the indicator set with each indicator's period/lookback parameters, the deterministic uptrend trend-gate rules and their thresholds (regime conditions, momentum conditions, the soft rising-volume bonus, and that a missing required indicator fails the gate), and the reversal-flag definitions and their thresholds, organised into readable grouped sections. While the configuration is loading the page SHALL show a loading state, and if the request fails it SHALL show an error state rather than a blank or broken page.

#### Scenario: Navigate to the Technical Indicators page

- **WHEN** a user selects the Technical Indicators navigation entry
- **THEN** the application SHALL render the Technical Indicators page within the shell and mark the entry active without a full page reload

#### Scenario: Configured setup displayed

- **WHEN** the Technical Indicators page loads the configuration successfully
- **THEN** it SHALL display the indicator set with their period/lookback parameters, the trend-gate rules and thresholds, and the reversal-flag definitions and thresholds in grouped sections

#### Scenario: Loading and error states

- **WHEN** the configuration is loading or the request fails
- **THEN** the page SHALL show a loading state while pending and an error state on failure instead of the configuration

### Requirement: Session-detail sector and category performance card

The paper-trading session detail view SHALL present a card showing the session's
performance attribution grouped by sector and by category, using the session's
sector/category performance breakdown. The card SHALL offer both groupings — by sector
and by category — and let the user view one at a time. For each group the card SHALL
display the group's total profit/loss as a money amount, its return as a percentage,
and a visual indication of the group's relative magnitude. Because a group's
profit/loss can be negative, the card SHALL use a sign-aware presentation (rows or
diverging bars with profit/loss distinguished by sign, consistent with the app's KPI
gain/loss styling) rather than a donut, which cannot represent negative contributions.
A group whose return is unavailable SHALL show a clear "not available" state for its
return instead of a numeric percentage. When the session has no positions to attribute,
the card SHALL show an empty state rather than an empty chart. The card SHALL reflect
the values returned by the breakdown each time the view loads.

#### Scenario: Performance card shown on the session page

- **WHEN** a user opens a paper-trading session that has positions
- **THEN** the view SHALL display a sector/category performance card listing each
  group's total P&L and return using the session's performance breakdown

#### Scenario: Switch between sector and category groupings

- **WHEN** the user toggles the card's grouping
- **THEN** the card SHALL show the performance grouped by sector or by category
  accordingly

#### Scenario: Gains and losses distinguished

- **WHEN** a group's total P&L is positive or negative
- **THEN** the card SHALL indicate the sign visually (gain versus loss), consistent with
  the app's KPI sign styling

#### Scenario: Group return unavailable

- **WHEN** a group's return is reported as unavailable
- **THEN** the card SHALL show a "not available" state for that group's return instead
  of a numeric percentage

#### Scenario: Empty state

- **WHEN** the session has no positions to attribute
- **THEN** the card SHALL show an empty state rather than an empty chart

### Requirement: System status view

The system SHALL provide a read-only "System Status" view, reachable from the shell navigation, that presents the status of each connected external backend (broker, web-search provider, market-data provider, AI model provider). For each backend the view SHALL show its name, whether it is configured, its non-secret identifier (such as broker mode, web-search provider, or model id), a clear reachable/unreachable/unavailable indication, and the probe latency when available; it SHALL NOT display any secret value. The view SHALL request fresh status on load, SHALL offer a manual refresh, and SHALL keep the status reasonably current by polling. While the status is first loading the view SHALL show a loading state, and if the status request itself fails the view SHALL show an error state and remain usable.

#### Scenario: View shows each backend's status

- **WHEN** a user opens the System Status view and the status loads
- **THEN** the view SHALL show, per backend, its name, configured state, non-secret identifier, a reachable/unreachable/unavailable indication, and its latency when available, without revealing any secret

#### Scenario: Manual refresh

- **WHEN** a user triggers the manual refresh on the System Status view
- **THEN** the view SHALL re-request the status and update the displayed results

#### Scenario: Loading and error states

- **WHEN** the status is loading for the first time, or the status request fails
- **THEN** the view SHALL show a loading indicator while pending and a meaningful error message on failure, remaining usable in either case

### Requirement: Increase a session's capital from the detail view

The paper-trading session detail view SHALL present, alongside the session's capital fact, a control that lets the user increase the session's capital by a positive amount. The control SHALL accept an amount, SHALL only permit increases (it SHALL NOT offer a withdrawal or a non-positive amount), and on confirmation SHALL request the increase. On success the UI SHALL refresh the session's capital-dependent figures (at least the displayed capital, the session's value and performance KPI tiles, and the value-history chart) so the added capital and its effect on returns are reflected. While the request is in flight the control SHALL indicate progress, and a failed request SHALL surface an error without leaving the view in an inconsistent state.

#### Scenario: Add capital from the detail view

- **WHEN** a user enters a positive amount in the add-capital control on the session detail view and confirms
- **THEN** the UI SHALL request the increase and, on success, refresh the displayed capital, the session's value/KPI tiles, and the value-history chart

#### Scenario: Non-positive amount is not submitted

- **WHEN** a user enters zero, a negative amount, or no amount in the add-capital control
- **THEN** the UI SHALL NOT request an increase

#### Scenario: In-flight progress indicated

- **WHEN** a capital-increase request is in flight
- **THEN** the control SHALL indicate progress

#### Scenario: Failed increase surfaces an error

- **WHEN** a capital-increase request fails
- **THEN** the UI SHALL surface an error and leave the session's displayed capital unchanged
