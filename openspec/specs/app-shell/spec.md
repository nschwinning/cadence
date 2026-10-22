# app-shell Specification

## Purpose
Provides the web application's persistent shell and navigation so users can move between the dashboard, assets, portfolios, and paper-trading views, and interact with asynchronous AI runs through a consistent, responsive interface.

## Requirements

### Requirement: Persistent application shell

The system SHALL present a persistent shell (header and sidebar navigation with the main content area) around every page. Navigation SHALL offer entries for Dashboard, Assets, Watchlist, Portfolios, Runs, and System, and SHALL indicate the active view. There SHALL be a single "Portfolios" entry for the unified portfolios-and-paper-trading area; there SHALL NOT be a separate "Paper Trading" entry. The shell SHALL be responsive, collapsing the sidebar on small viewports.

#### Scenario: Navigate between views

- **WHEN** a user selects a navigation entry
- **THEN** the application SHALL render that view within the shell and mark the entry active without a full page reload

#### Scenario: Single Portfolios navigation entry

- **WHEN** a user views the sidebar navigation
- **THEN** the navigation SHALL show one "Portfolios" entry for the merged area and SHALL NOT show a separate "Paper Trading" entry

#### Scenario: Small viewport

- **WHEN** the viewport is narrow
- **THEN** the sidebar SHALL collapse into a toggleable menu

### Requirement: Asset management views

The system SHALL provide a view to add an asset, browse the paginated/searchable/filterable asset list, and open an asset's detail (including its recent price history and profile). Errors from the API (duplicate, unknown ticker, data unavailable) SHALL be surfaced to the user with a meaningful message. In the asset list, each asset that is not tradable on Alpaca — a foreign or otherwise unpriceable listing, identified by the absence of a resolved Alpaca symbol — SHALL be visually flagged as not tradable, distinct from the asset's eligibility status; assets that are tradable on Alpaca SHALL NOT carry that flag.

#### Scenario: Add and browse assets

- **WHEN** a user adds a ticker and browses the list
- **THEN** the newly added asset SHALL appear in the list and be openable in a detail view

#### Scenario: Add error surfaced

- **WHEN** adding a ticker returns a duplicate/unknown/unavailable error
- **THEN** the UI SHALL display a corresponding message and remain usable

#### Scenario: Not-tradable asset is flagged in the list

- **WHEN** a user browses the asset list and an asset has no resolved Alpaca symbol (a foreign or unpriceable listing)
- **THEN** the UI SHALL show a not-tradable indicator on that asset's row, separate from its eligibility status, that explains the asset cannot be traded on Alpaca and should be replaced with a tradable US listing

#### Scenario: Tradable asset is not flagged

- **WHEN** a user browses the asset list and an asset has a resolved Alpaca symbol
- **THEN** the UI SHALL NOT show the not-tradable indicator on that asset's row

### Requirement: AI run views with polling

The system SHALL let a user start asynchronous AI runs (recommendations, portfolio build, rebalance) and SHALL poll their status until a terminal state, reflecting progress and final outcome in the UI without manual refresh.

#### Scenario: Start and follow a run

- **WHEN** a user starts an AI recommendation, build, or rebalance
- **THEN** the UI SHALL show it as in-progress and SHALL automatically update to the final result when the run reaches a terminal state

### Requirement: Watchlist table view

The system SHALL provide a Watchlist view that lets the user trigger an
AI-driven watchlist recommendation run and browse the resulting watchlist
entries. Triggering a run SHALL reuse the asynchronous AI-run polling behavior
(showing the run as in-progress and updating to its terminal outcome without a
manual refresh). The view SHALL present the watchlist assets (those with
`watchlist` membership, kept separate from the universe/Assets view) as a
**searchable, sortable, and filterable table** mirroring the Assets list: a
text search over ticker/name, sortable ticker and name columns, and
category/sector filters. Each row SHALL link to that asset's detail view, where
the asset's fundamentals and technical indicators are shown. The watchlist view
SHALL NOT render each entry's fundamentals or technical-indicator values inline
in the list (those are surfaced on the asset detail view). Errors from the API
SHALL be surfaced with a meaningful message.

#### Scenario: Trigger a watchlist recommendation

- **WHEN** a user starts an AI watchlist recommendation from the Watchlist view
- **THEN** the UI SHALL show the run as in-progress and SHALL automatically
  update to its final outcome when the run reaches a terminal state

#### Scenario: Browse the watchlist as a table

- **WHEN** a user opens the Watchlist view with watchlist assets present
- **THEN** the UI SHALL list those entries in a table that can be searched by
  ticker/name, sorted by ticker and name, and filtered by category and sector

#### Scenario: Jump from a watchlist row to the asset detail

- **WHEN** a user selects a watchlist entry's row
- **THEN** the UI SHALL open that asset's detail view, where its fundamentals
  and technical indicators are shown

#### Scenario: Watchlist is separate from the universe

- **WHEN** a user views the Assets (universe) list and the Watchlist view
- **THEN** watchlist assets SHALL appear only in the Watchlist view and SHALL
  NOT appear in the universe asset list

### Requirement: Asset detail fundamentals and technical indicators

The asset detail view SHALL display, for the opened asset, its available SEC
EDGAR fundamentals (for example revenue, margins, cash flow, earnings, and
company details), indicating when the asset's fundamentals are unavailable. The
asset detail view SHALL also display the asset's **short-window
technical-indicator profile** (the momentum/mean-reversion subset — for example
RSI, MACD, EMA, Bollinger, historical volatility, and volume signals), and SHALL
show an explicit **insufficient-history** state when the asset's price history is
below the technical minimum-history floor rather than rendering mostly-empty
indicator values. These sections SHALL render for any asset (universe or
watchlist) through the same detail view. The asset detail view SHALL NOT present
a long-window uptrend trend-gate verdict as a buy/sell signal. Errors loading the
fundamentals or technical data SHALL be surfaced with a meaningful message and
SHALL NOT prevent the rest of the detail view from rendering.

#### Scenario: Detail shows fundamentals when available

- **WHEN** a user opens the detail view for an asset that has fundamentals
- **THEN** the UI SHALL display that asset's available fundamentals

#### Scenario: Detail indicates unavailable fundamentals

- **WHEN** a user opens the detail view for an asset whose fundamentals could not be fetched or do not exist
- **THEN** the UI SHALL indicate that the asset's fundamentals are unavailable rather than showing empty values

#### Scenario: Detail shows the short-window technical profile

- **WHEN** a user opens the detail view for an asset whose history is at or above the technical minimum-history floor and whose indicator snapshot exists
- **THEN** the UI SHALL display that asset's short-window technical-indicator profile

#### Scenario: Detail shows an insufficient-history state

- **WHEN** a user opens the detail view for an asset whose history is below the technical minimum-history floor
- **THEN** the UI SHALL show an explicit insufficient-history state for the technical indicators rather than mostly-empty values

### Requirement: Portfolio and paper-trading views

The system SHALL provide a single unified **Portfolios** area — one list view and one per-session detail view — replacing the previously separate portfolio and paper-trading views. The unified list SHALL be session-driven: each row is a paper-trading session, and the list SHALL present, alongside each session's status, allocated capital, trade count, current portfolio value, realised profit/loss, and unrealised profit/loss, the portfolio-definition attributes of the session's portfolio — its risk profile and its number of holdings. The list's per-row current portfolio value, realised profit/loss, and unrealised profit/loss SHALL be marked to market from live quotes on an all-time basis, using the same definition of the three figures as the session detail view's performance KPIs (current value is the net asset value net of fees, realised profit/loss is the cumulative closed-lot realised profit/loss, and unrealised profit/loss is the current mark-to-market gain or loss on open positions). The list SHALL show the AI portfolio build form and the multi-session performance-comparison chart above the table. Opening a row SHALL navigate to the session's detail view at `/portfolios/:id`, where the identifier is the session's id. The session list and the session detail header SHALL identify each session by its portfolio name as the primary label, and SHALL present the strategy as secondary context rather than the primary identifier. When a session has no resolvable portfolio name, the UI SHALL fall back to the strategy label. The session detail view SHALL display its trades, runs, positions, and AI-portfolio events. The session detail view SHALL additionally display the session's **portfolio definition**, resolved via the session's portfolio reference: an overview of the portfolio's source, risk profile, maximum allocation, number of holdings, creation time, and source run, together with a holdings list whose tickers each link to the asset's detail view; when the session has no resolvable portfolio, the detail view SHALL still render the session content and SHALL omit the portfolio-definition section rather than erroring. The session detail view SHALL display the session's **AI model** — the model its AI runs execute on, shown by its catalog display name. The session detail view SHALL display the session's **automatic stop-loss configuration** — whether it is enabled and, when enabled, its threshold percentage. The session detail view SHALL display the session's **risk-guardrail configuration** — whether the guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage. The session detail view SHALL display the session's **learning-feedback configuration** — whether learning feedback (informing the rebalance agent of the session's recent prior-run outcomes) is enabled and, when enabled, its learning window (number of recent days). The session detail view SHALL display the session's **company-fundamentals configuration** — whether company fundamentals (supplying the rebalance agent with per-ticker company financials) are enabled. The session detail view SHALL display the session's **watchlist-inclusion configuration** — whether the candidate universe the AI picks from includes the user's watchlist-membership assets. The session detail view SHALL display the session's **technical-indicator configuration** — whether the technical-indicator trend strategy (restricting entries to assets in a confirmed uptrend and attaching trend context to holdings on the build and every rebalance) is enabled. Among the session's trades and runs, those produced by the automatic stop-loss SHALL be identifiable as stop-loss activity (rather than AI-driven build or rebalance activity). On the session detail view, a run that was produced by an AI build or rebalance SHALL link to that run's detail view; a run not backed by an AI-portfolio event SHALL remain non-interactive. The legacy `/paper-trading` and `/paper-trading/:id` paths SHALL redirect to `/portfolios` and `/portfolios/:id` respectively, preserving the identifier, so existing links continue to work.

On the session detail view, each of the four tables — AI-portfolio events, trades, closed positions, and runs — SHALL show one fixed-size page of rows at a time rather than a single unbounded list, with the first page showing the most recent rows. The default page size SHALL be 5 rows for the AI-portfolio events and runs tables and 10 rows for the trades and closed-positions tables. Each table SHALL provide page-through navigation (moving to the previous and next page, without infinite scroll) and SHALL indicate the user's position within the whole (for example, the current page relative to the total number of pages or rows). When a table has no more than one page of rows, its navigation SHALL convey that there are no further pages. Paging one table SHALL NOT change the page shown by the other tables.

#### Scenario: Inspect a paper-trading session

- **WHEN** a user opens a paper-trading session
- **THEN** the UI SHALL display its trades, runs, positions, and the AI decision events for that session

#### Scenario: Single unified Portfolios list

- **WHEN** a user opens the Portfolios area
- **THEN** the UI SHALL show one session-driven list of the user's portfolios (one row per paper-trading session) rather than separate portfolio and paper-trading lists

#### Scenario: List shows portfolio definition alongside performance

- **WHEN** a user views the unified Portfolios list
- **THEN** each row SHALL show the session's status, allocated capital, trade count, current portfolio value, realised profit/loss, and unrealised profit/loss together with the portfolio's risk profile and its number of holdings

#### Scenario: List shows live marked-to-market value and P&L

- **WHEN** a user views the unified Portfolios list for a session holding open positions
- **THEN** that row's current value, realised profit/loss, and unrealised profit/loss SHALL be marked to market from live quotes (not a stale stored valuation), consistent with the figures the session's detail view shows

#### Scenario: List shows the build form and comparison chart

- **WHEN** a user opens the unified Portfolios list
- **THEN** the UI SHALL present the AI portfolio build form and the multi-session performance-comparison chart above the list table

#### Scenario: Detail folds in the portfolio definition

- **WHEN** a user opens a session's detail view and the session has a resolvable portfolio
- **THEN** the UI SHALL display the portfolio's overview (source, risk profile, maximum allocation, number of holdings, creation time, and source run) and a holdings list whose tickers each link to the asset's detail view

#### Scenario: Detail for a session with no resolvable portfolio

- **WHEN** a user opens a session's detail view and the session has no resolvable portfolio
- **THEN** the UI SHALL still render the session content and SHALL omit the portfolio-definition section rather than showing an error

#### Scenario: Legacy paper-trading routes redirect

- **WHEN** a user navigates to `/paper-trading` or `/paper-trading/:id`
- **THEN** the UI SHALL redirect to `/portfolios` or `/portfolios/:id` respectively, preserving the identifier

#### Scenario: Sessions are labeled by portfolio

- **WHEN** a user views the unified Portfolios list or a session's detail header
- **THEN** the UI SHALL show the portfolio name as the primary label and the strategy as secondary context

#### Scenario: Fallback when portfolio name is missing

- **WHEN** a session has no resolvable portfolio name
- **THEN** the UI SHALL show the strategy label in place of the portfolio name

#### Scenario: Session shows its model

- **WHEN** a user opens a session's detail view
- **THEN** the UI SHALL display the AI model the session runs on, by its catalog display name

#### Scenario: Session shows its stop-loss configuration

- **WHEN** a user opens a session's detail view
- **THEN** the UI SHALL display whether the automatic stop-loss is enabled and, when enabled, its threshold percentage

#### Scenario: Session shows its guardrail configuration

- **WHEN** a user opens a session's detail view for a session built with the risk guardrails enabled
- **THEN** the UI SHALL display that the guardrails are enabled together with the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage

#### Scenario: Session shows guardrails disabled

- **WHEN** a user opens a session's detail view for a session built without the risk guardrails
- **THEN** the UI SHALL indicate that the risk guardrails are disabled

#### Scenario: Session shows its learning-feedback configuration

- **WHEN** a user opens a session's detail view
- **THEN** the UI SHALL indicate whether learning feedback is enabled for that session and, when enabled, its learning window

#### Scenario: Session shows its fundamentals configuration

- **WHEN** a user opens a session's detail view
- **THEN** the UI SHALL indicate whether company fundamentals are enabled for that session

#### Scenario: Session shows its watchlist-inclusion configuration

- **WHEN** a user opens a session's detail view
- **THEN** the UI SHALL indicate whether the session's candidate universe includes watchlist-membership assets

#### Scenario: Session shows its technical-indicator configuration

- **WHEN** a user opens a session's detail view
- **THEN** the UI SHALL indicate whether the technical-indicator trend strategy is enabled for that session

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

The system SHALL provide a Runs view that lists AI runs (build and rebalance) across all sessions, newest first, showing at least each run's type, status, number of orders executed, and time, and SHALL let a user open a run to a detail view. The run detail view SHALL show the run's AI reasoning, the AI model that produced the run (by its catalog display name), its research (each web search's query and results), the trades the run opened, the positions the run closed, and — when the run recorded trend-decision context — the technical-indicator picture behind the run: the candidates that were filtered out by the trend gate (each with the reason it failed) and the indicator annotations that were handed to the AI for the surviving candidates and for the current holdings (including the holdings' reversal flags). When a run recorded no trend-decision context, the detail view SHALL simply omit that section rather than show an error.

#### Scenario: Browse runs

- **WHEN** a user opens the Runs view
- **THEN** the UI SHALL list AI runs across all sessions newest first and allow opening any run's detail

#### Scenario: Inspect a run

- **WHEN** a user opens a run's detail
- **THEN** the UI SHALL display the run's reasoning, the model that produced it, its research (queries and results), the trades it opened, and the positions it closed

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

When the chart is rendered, it SHALL display a **labelled x-axis** marking several
calendar dates spread across the plotted history — more than just the first and last
points — and a **labelled y-axis** marking portfolio value in USD, so a user can read
what any point on a line represents. Axis tick labels SHALL be rendered legibly (not
distorted by the chart's scaling). The chart SHALL also show a **legend** identifying
which line is the session's portfolio value and which line is the benchmark; when the
benchmark line is not drawn, the legend SHALL not imply a benchmark line is present.

The value history chart SHALL display an **end-of-day indicator** (for example, an "End
of day" badge beside the chart heading) communicating that the chart reflects end-of-day
value snapshots and that its latest point is the most recent snapshot (the prior close),
together with a brief explanatory hint that it can lag the live performance tiles
intraday. The indicator SHALL NOT change any plotted value.

When the chart is rendered with plottable history, it SHALL support **hover
inspection**: moving the pointer over the plot area SHALL identify the plotted snapshot
nearest the pointer's horizontal position and SHALL show a tooltip reporting that
snapshot's **date** and its **portfolio value** in USD, and — when a benchmark value
exists at that snapshot — the **benchmark value** in USD. The tooltip SHALL be rendered
legibly (not distorted by the chart's scaling) and SHALL be positioned near the hovered
point without being clipped out of the chart area. The chart MAY also mark the hovered
point visually (for example, a crosshair or dot). When the pointer leaves the plot area,
the tooltip SHALL be dismissed. Hover inspection SHALL NOT change any plotted value and
SHALL NOT appear when the placeholder, loading, or error state is shown.

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
- **THEN** the view SHALL show several dated x-axis labels spread across the history — more than just the endpoints — and USD y-axis labels around the plot area

#### Scenario: Legend identifies each line

- **WHEN** the value chart is rendered
- **THEN** the view SHALL show a legend naming the portfolio-value line and, when it is drawn, the benchmark line, each keyed to its line's colour or style

#### Scenario: Hover reveals a snapshot's value and date

- **WHEN** a user moves the pointer over the rendered value chart
- **THEN** the view SHALL show a tooltip reporting the nearest snapshot's date and its portfolio value in USD, and the benchmark value in USD when a benchmark value exists at that snapshot

#### Scenario: Tooltip dismisses on leave

- **WHEN** the pointer leaves the value chart's plot area
- **THEN** the view SHALL dismiss the hover tooltip

#### Scenario: Not enough history

- **WHEN** a user opens a session that has fewer than two value snapshots
- **THEN** the view SHALL show a placeholder indicating there is not yet enough
  history to chart

#### Scenario: Loading and error states

- **WHEN** the session's value history is loading or fails to load
- **THEN** the view SHALL show a loading or error state instead of the chart

### Requirement: Archive controls for sessions and portfolios

The UI SHALL let a user archive and unarchive paper-trading sessions from the unified Portfolios area. The unified Portfolios list and the session detail view SHALL each offer an archive action for an eligible session and an unarchive action for an archived session; the session archive action SHALL be available only for a stopped session. The UI SHALL NOT present a separate portfolio-archive control — archiving is managed through the session. Archived sessions SHALL be hidden from the default Portfolios list, and the list SHALL provide a "Show archived" toggle that reveals archived sessions and visibly marks them as archived. After archiving or unarchiving, the list SHALL reflect the change without requiring a manual page reload.

#### Scenario: Archive a stopped session from the UI

- **WHEN** a user invokes the archive action on a stopped session
- **THEN** the UI SHALL archive the session and remove it from the default Portfolios list

#### Scenario: Show and unarchive archived items

- **WHEN** a user enables the "Show archived" toggle on the Portfolios list
- **THEN** the UI SHALL display archived sessions marked as archived and SHALL offer an unarchive action that restores a session to the default list

#### Scenario: Archive action limited to eligible items

- **WHEN** a user views a session that is active or paused
- **THEN** the UI SHALL NOT offer an enabled archive action for that session

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

### Requirement: AI build form asset scope and default capital

The AI portfolio build form SHALL be opened from a control on the Portfolios page and presented in a modal dialog rather than rendered inline on the page, so the page is not cluttered by the form when the user is not building a portfolio; the modal SHALL be dismissible via an explicit close control, a click on the backdrop, and the Escape key. The build form SHALL NOT offer a daily-rebalancing enrollment choice — every AI portfolio is enrolled in daily rebalancing automatically — and MAY note that all AI portfolios rebalance daily. The AI portfolio build form SHALL let the user choose the portfolio's asset scope — stocks only, crypto only, or both — defaulting to both, and SHALL let the user choose the session's benchmark from the fixed benchmark catalog, defaulting to S&P 500. The form SHALL also let the user choose the session's **AI model** from the fixed model catalog, defaulting to the configured default model. The form SHALL also let the user opt the portfolio into the **technical-indicator trend strategy** via a toggle that defaults to **off**. The form SHALL also let the user opt the portfolio into **company fundamentals** via a toggle that defaults to **off**, which when enabled supplies the session's rebalance agent with per-ticker company financials. The form SHALL also let the user opt the portfolio into **including watchlist assets** via a toggle that defaults to **off**, which when enabled adds the user's watchlist-membership assets to the candidate universe the session's AI picks from. The form SHALL also let the user opt the portfolio into an **automatic hard stop-loss** via a toggle that defaults to **off**, and SHALL let the user set the **stop-loss threshold percentage** (defaulting to the configured default) that applies when the stop-loss is enabled; the threshold control MAY be hidden or disabled while the stop-loss toggle is off. The form SHALL also let the user opt the portfolio into **portfolio risk guardrails** via a toggle that defaults to **off**, and SHALL let the user set the guardrail parameters that apply when the guardrails are enabled — the **maximum percentage per asset**, the **maximum percentage per asset class**, the **minimum number of positions**, and the **maximum invested percentage** (cash buffer) — each defaulting to its configured default; the guardrail parameter controls MAY be hidden or disabled while the guardrail toggle is off. The form SHALL also let the user opt the portfolio into **learning feedback** via a toggle that defaults to **off**, which when enabled informs the session's rebalance agent of its own recent prior-run outcomes, and SHALL let the user set the **learning window** (number of recent days, defaulting to the configured default) that applies when learning feedback is enabled; the window control MAY be hidden or disabled while the learning-feedback toggle is off. The form's allocated-capital input SHALL default to the configured default amount (10,000). The chosen asset scope SHALL be sent with the build request so the resulting portfolio is restricted to the selected asset types, the chosen benchmark SHALL be sent with the build request so the session is compared against it, the chosen model SHALL be sent with the build request so the session's AI runs execute on it, the technical-indicator opt-in SHALL be sent with the build request so the resulting session applies (or omits) the trend strategy accordingly, the company-fundamentals opt-in SHALL be sent with the build request so the resulting session enables (or omits) the fundamentals block accordingly, the watchlist-inclusion opt-in SHALL be sent with the build request so the resulting session includes (or omits) watchlist assets in its candidate universe accordingly, the stop-loss opt-in and (when enabled) threshold SHALL be sent with the build request so the resulting session applies (or omits) the automatic stop-loss accordingly, and the risk-guardrail opt-in and (when enabled) its parameters SHALL be sent with the build request so the resulting session applies (or omits) the guardrails accordingly, and the learning-feedback opt-in and (when enabled) its window SHALL be sent with the build request so the resulting session enables (or omits) learning feedback accordingly.

#### Scenario: Opening the build form opens a modal

- **WHEN** a user activates the "Build an AI portfolio" control on the Portfolios page
- **THEN** the build form SHALL be presented in a modal dialog overlaying the page rather than inline

#### Scenario: Dismissing the build modal

- **WHEN** the build modal is open and the user activates its close control, clicks the backdrop, or presses the Escape key
- **THEN** the modal SHALL be dismissed and the Portfolios page SHALL be shown without the form

#### Scenario: Form offers no daily-rebalancing choice

- **WHEN** a user opens the AI portfolio build form
- **THEN** the form SHALL NOT present any daily-rebalancing enrollment control, and the build request it submits SHALL carry no daily-rebalancing option

#### Scenario: Default form values

- **WHEN** a user opens the AI portfolio build form
- **THEN** the capital input SHALL default to 10,000, the asset scope SHALL default to both (stocks and crypto), the benchmark SHALL default to S&P 500, the model SHALL default to the configured default model, the technical-indicator trend-strategy toggle SHALL default to off, the company-fundamentals toggle SHALL default to off, the include-watchlist-assets toggle SHALL default to off, the automatic stop-loss toggle SHALL default to off, the risk-guardrails toggle SHALL default to off, the learning-feedback toggle SHALL default to off, and the learning-window control SHALL default to the configured default

#### Scenario: Selecting an asset scope

- **WHEN** a user selects stocks only (or crypto only) and submits the build form
- **THEN** the UI SHALL send the selected asset scope with the build request

#### Scenario: Selecting a benchmark

- **WHEN** a user selects a benchmark from the catalog and submits the build form
- **THEN** the UI SHALL send the selected benchmark with the build request

#### Scenario: Selecting a model

- **WHEN** a user selects a model from the model catalog and submits the build form
- **THEN** the UI SHALL send the selected model with the build request so the resulting session's AI runs execute on it

#### Scenario: Opting into the technical-indicator trend strategy

- **WHEN** a user enables the technical-indicator trend-strategy toggle and submits the build form
- **THEN** the UI SHALL send the technical-indicator opt-in with the build request so the resulting session applies the trend strategy

#### Scenario: Leaving the trend strategy off

- **WHEN** a user submits the build form without enabling the technical-indicator toggle
- **THEN** the UI SHALL send the build request with the opt-in off so the resulting session does not apply the trend strategy

#### Scenario: Opting into company fundamentals

- **WHEN** a user enables the company-fundamentals toggle and submits the build form
- **THEN** the UI SHALL send the company-fundamentals opt-in with the build request so the resulting session supplies the fundamentals block to its rebalance agent

#### Scenario: Leaving company fundamentals off

- **WHEN** a user submits the build form without enabling the company-fundamentals toggle
- **THEN** the UI SHALL send the build request with the fundamentals opt-in off so the resulting session supplies no fundamentals block

#### Scenario: Opting into including watchlist assets

- **WHEN** a user enables the include-watchlist-assets toggle and submits the build form
- **THEN** the UI SHALL send the watchlist-inclusion opt-in with the build request so the resulting session includes the user's watchlist-membership assets in its candidate universe

#### Scenario: Leaving watchlist assets off

- **WHEN** a user submits the build form without enabling the include-watchlist-assets toggle
- **THEN** the UI SHALL send the build request with the watchlist-inclusion opt-in off so the resulting session's candidate universe excludes watchlist-membership assets

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

#### Scenario: Opting into learning feedback

- **WHEN** a user enables the learning-feedback toggle, sets a learning window, and submits the build form
- **THEN** the UI SHALL send the learning-feedback opt-in and the chosen window with the build request so the resulting session enables learning feedback with that window

#### Scenario: Leaving learning feedback off

- **WHEN** a user submits the build form without enabling the learning-feedback toggle
- **THEN** the UI SHALL send the build request with learning feedback off so the resulting session does not apply learning feedback

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

The paper-trading session list view SHALL display a **performance-comparison chart** that overlays every non-archived session (active, paused, stopped) on a shared time axis, so a user can compare sessions and see which performs best. The chart SHALL plot one line per session that has at least two value points, sharing a single y-scale across all plotted lines, and SHALL show a **legend** mapping each line's color to its session label. The chart's lines and its legend SHALL be ordered by session creation date, oldest first, and each session's color SHALL be keyed to the session's stable identity so a given session keeps the same color across renders. Sessions with fewer than two value points SHALL appear in the legend but SHALL NOT be plotted. The chart SHALL offer a **metric toggle** with two views, defaulting to the return view:

- **Return %** (default): each session's line SHALL be its cumulative total-return percentage, computed from the session's total value relative to its allocated capital, so sessions with different allocated capital and start dates are compared fairly and the highest line is the best performer.
- **Value ($)**: each session's line SHALL be its absolute total portfolio value in USD.

When the chart plots at least one line, it SHALL display a **labelled x-axis** marking several calendar dates spread across the shared time axis — more than just the first and last points — and a **labelled y-axis** whose tick labels match the active metric — percentages in the Return % view and USD amounts in the Value $ view — and the y-axis labels SHALL update when the metric toggle switches. Axis tick labels SHALL be rendered legibly (not distorted by the chart's scaling).

When the chart plots at least one line, it SHALL support **hover inspection**: moving the pointer over the plot area SHALL identify the plotted point nearest the pointer across all plotted session lines and SHALL show a tooltip reporting that point's **session label**, its **date**, and its **value** formatted for the active metric — a percentage in the Return % view and a USD amount in the Value $ view. The tooltip SHALL be rendered legibly (not distorted by the chart's scaling) and SHALL be positioned near the hovered point without being clipped out of the chart area. The chart MAY also mark the hovered point visually. When the pointer leaves the plot area, the tooltip SHALL be dismissed. Hover inspection SHALL NOT change any plotted value and SHALL NOT appear when the insufficient-data placeholder, loading, or error state is shown.

When no non-archived session has enough value points to plot, the chart SHALL show an insufficient-data placeholder rather than an empty plot area. The chart SHALL show its own loading and error states while the comparison data is being fetched or if the fetch fails. The existing single-session value chart on the session detail view SHALL remain unchanged.

#### Scenario: Comparison chart overlays non-archived sessions

- **WHEN** a user opens the paper-trading session list and multiple non-archived sessions each have at least two value points
- **THEN** the chart SHALL render one line per such session on a shared y-scale with a legend identifying each session by its label

#### Scenario: Lines and legend are ordered oldest-created first

- **WHEN** the comparison chart renders lines for several sessions
- **THEN** the chart's lines and its legend SHALL be ordered by session creation date, oldest first

#### Scenario: Toggle between return % and absolute value

- **WHEN** a user switches the metric toggle from the default return view to the value view
- **THEN** the chart SHALL re-plot each session's line as its absolute portfolio value in USD, and switching back SHALL re-plot cumulative total-return percentage

#### Scenario: Return view is the default

- **WHEN** the comparison chart first renders
- **THEN** it SHALL show the cumulative total-return percentage view by default

#### Scenario: Axes are labelled and track the metric

- **WHEN** the comparison chart plots at least one line
- **THEN** the view SHALL show several dated x-axis labels spread across the time axis — more than just the endpoints — and y-axis labels formatted as percentages in the Return % view and as USD amounts in the Value $ view, and the y-axis labels SHALL change when the metric toggle is switched

#### Scenario: Hover reveals the nearest series point

- **WHEN** a user moves the pointer over the rendered comparison chart
- **THEN** the view SHALL show a tooltip reporting the nearest plotted point's session label, its date, and its value formatted as a percentage in the Return % view or a USD amount in the Value $ view

#### Scenario: Tooltip value tracks the metric toggle

- **WHEN** a user hovers the comparison chart and then switches the metric toggle
- **THEN** the hover tooltip's value SHALL be formatted for the active metric — a percentage in the Return % view and a USD amount in the Value $ view

#### Scenario: Tooltip dismisses on leave

- **WHEN** the pointer leaves the comparison chart's plot area
- **THEN** the view SHALL dismiss the hover tooltip

#### Scenario: Session with too little history is legended but not plotted

- **WHEN** a non-archived session has fewer than two value points
- **THEN** that session SHALL appear in the legend but SHALL NOT be drawn as a line

#### Scenario: Insufficient data placeholder

- **WHEN** no non-archived session has at least two value points
- **THEN** the chart SHALL display an insufficient-data placeholder instead of an empty plot

#### Scenario: Loading and error states

- **WHEN** the comparison data is loading, or the request fails
- **THEN** the chart SHALL show a loading indicator while pending and an error state on failure, rather than a blank or broken chart

### Requirement: Stable paper-trading session ordering and per-portfolio chart color

Paper-trading sessions SHALL be presented in one stable, predictable order everywhere they are listed or plotted, and each session SHALL keep one stable color in the comparison chart, so a returning user can recognise a given portfolio by its position and its color rather than seeing them reshuffle between visits.

The paper-trading **session list** SHALL order sessions by their creation date, oldest first. This order SHALL NOT depend on when a session was last updated, rebalanced, or otherwise touched, so adding a new session appends it at the end rather than reordering the existing ones.

The **comparison chart's lines and its legend** SHALL be ordered by session creation date, oldest first, consistent with the session list.

Each session's **line color** in the comparison chart SHALL be derived from the session's own stable identity, not from its position in the current render. The same session SHALL therefore be drawn in the same color across page visits and regardless of which other sessions are currently plotted or which sessions are archived.

#### Scenario: Session list is ordered oldest-created first

- **WHEN** a user views the paper-trading session list with multiple sessions
- **THEN** the sessions SHALL be ordered by creation date, oldest first, independent of when each was last updated

#### Scenario: A new session appends without reordering

- **WHEN** a new session is created and the user reloads the session list
- **THEN** the new session SHALL appear at the end of the list and the existing sessions SHALL keep their previous relative order

#### Scenario: Comparison chart order matches the list

- **WHEN** the comparison chart renders lines for several sessions
- **THEN** the chart's lines and its legend SHALL be ordered by session creation date, oldest first, consistent with the session list

#### Scenario: A portfolio keeps its color across visits

- **WHEN** a user views the comparison chart, leaves, and returns — or when the set of plotted sessions changes (for example a session is archived)
- **THEN** each session that is still plotted SHALL be drawn in the same color as before, because its color is keyed to the session's stable identity rather than its render position

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

The Dashboard SHALL present a single range selector offering the choices `1D`, `1W`, `1M`, `YTD`, `1Y`, and `Max`, with one range active at a time. Changing the selected range SHALL drive every range-dependent section of the Dashboard (performance tiles, equity curve, portfolio leaderboard, automation failed-run count, recent activity, and universe performers) so that the whole view answers for the same horizon. The universe balance summary is range-independent and SHALL NOT change with the selector. The point-in-time current portfolio value is range-independent and SHALL NOT change with the selector. The range selector SHALL be presented in association with the range-scoped performance region (rather than only beside the page title) so that its scope — the range-dependent figures, not the point-in-time current value or the current-composition universe balance — is evident to the user.

#### Scenario: Selecting a range updates the whole dashboard

- **WHEN** a user selects a different range
- **THEN** the performance tiles, equity curve, leaderboard, recent activity, and universe performers SHALL all refresh to that range while the universe balance summary and the point-in-time current value stay unchanged

#### Scenario: Selector presented with the performance region

- **WHEN** the Dashboard renders the range selector
- **THEN** it SHALL be presented in association with the range-scoped performance region so its governance over the range-dependent figures is evident, rather than implying it governs the point-in-time current value or the current-composition universe balance

### Requirement: Dashboard aggregate performance tiles

The Dashboard SHALL present, for the active sessions currently selected in the equity curve, a point-in-time value band of **four** figures, marked as current/live and shown separately from the range-scoped performance tiles: the aggregate **current portfolio value** (the summed current value of the selected sessions), the aggregate **since-inception total return** as a percentage, the aggregate **since-inception lifetime profit/loss** as a dollar amount, and the aggregate **since-inception return versus benchmark** as an excess-return percentage. These four figures are point-in-time and SHALL reflect the current portfolio selection but SHALL NOT change with the range. The value band SHALL span the full page width and lay the four tiles out responsively (dividing the width on wide viewports, stacking on narrow ones).

The aggregate since-inception total return SHALL be the summed current value of the selected sessions minus their summed contributed capital, divided by their summed contributed capital, where a session's contributed capital is the sum of its capital contributions (opening capital plus any later capital increases). The aggregate lifetime profit/loss SHALL be the summed current value minus the summed contributed capital. The aggregate return versus benchmark SHALL be the aggregate since-inception total return minus the aggregate benchmark buy-and-hold return, where the benchmark leg sums, over the selected sessions, each session's since-inception buy-and-hold of its contributions in its **own** benchmark; when any selected session lacks a priceable benchmark value, the return-versus-benchmark tile SHALL show a clear "not yet available" state rather than a figure. The total return, lifetime profit/loss, and return-versus-benchmark figures SHALL be visually distinguished by sign (gain versus loss; outperformance versus underperformance).

The Dashboard SHALL also present range-scoped performance tiles showing, over the selected range, the summed realised profit/loss, the summed unrealised profit/loss, the money-weighted return, and the fees incurred within the range, grouped together under an indication of the active range. The summed realised and unrealised tiles SHALL use the per-session range-relative realised and unrealised profit/loss summed across the selected sessions, and SHALL be visually distinguished by sign (gain versus loss). The range-scoped tiles SHALL reflect the current portfolio selection and the selected range; the point-in-time value band SHALL reflect the current selection but SHALL NOT change with the range. The realised and unrealised figures are shown as two independent amounts and are not presented as an additive breakdown of the range return.

#### Scenario: Current value shown as point-in-time

- **WHEN** the Dashboard renders the aggregate performance tiles
- **THEN** the aggregate current portfolio value SHALL be shown in the point-in-time value band, separately from the range-scoped tiles, and marked as a current/live figure that does not change when the range changes

#### Scenario: Value band presents four point-in-time figures

- **WHEN** the Dashboard renders the point-in-time value band for the selected sessions
- **THEN** it SHALL present four live tiles — aggregate current value, aggregate since-inception total return percentage, aggregate since-inception lifetime profit/loss amount, and aggregate since-inception return versus benchmark — spanning the full page width

#### Scenario: Value-band figures are range-independent

- **WHEN** a user changes the range
- **THEN** the four point-in-time value-band figures SHALL NOT change, while the range-scoped tiles recompute for the new range

#### Scenario: Value-band figures reflect the selection

- **WHEN** a user changes the set of selected portfolios
- **THEN** the aggregate current value, total return, lifetime profit/loss, and return versus benchmark SHALL recompute over the newly selected sessions from already-fetched data without a new request

#### Scenario: Since-inception figures distinguished by sign

- **WHEN** the aggregate since-inception total return, lifetime profit/loss, or return versus benchmark for the selected sessions is positive or negative
- **THEN** the corresponding tile SHALL indicate the sign visually (gain versus loss; outperformance versus underperformance)

#### Scenario: Return versus benchmark unavailable

- **WHEN** any selected session has no priceable since-inception benchmark value
- **THEN** the return-versus-benchmark tile SHALL show a clear "not yet available" state rather than a figure

#### Scenario: Tiles reflect range and selection

- **WHEN** a user changes the range or the set of selected portfolios
- **THEN** the range-scoped tiles SHALL recompute to show summed range realised P&L, summed range unrealised P&L, money-weighted range return, and range fees for the selected sessions, grouped under an indication of the active range

#### Scenario: Realised and unrealised tiles distinguished by sign

- **WHEN** the summed range realised or unrealised profit/loss for the selected sessions is positive or negative
- **THEN** the corresponding tile SHALL indicate the sign visually (gain versus loss)

### Requirement: Dashboard combined equity curve

The Dashboard SHALL present a combined equity curve as a single line equal to the summed value of the selected active sessions over the selected range, on a common date axis. A session SHALL contribute zero before its first recorded value (carry-forward thereafter). The Dashboard SHALL offer a selectable list of the active sessions, all selected by default, letting the user include or exclude each session; the selection SHALL also drive the hero tiles and the leaderboard. Toggling a session SHALL re-aggregate from already-fetched per-session data without issuing a new request per toggle. When no session is selected, the chart SHALL show an empty state instead of a line.

The chart SHALL also overlay **benchmark index lines** on the same dollar axis. It SHALL present a benchmark legend listing every index in the benchmark catalog, each individually selectable, with the S&P 500 selected by default and the others deselected. For each selected benchmark that has price data over the range, the chart SHALL draw a line equal to the **sum over the selected sessions of a buy-and-hold of each session's contributed capital in that index** — for each selected session, its opening capital is treated as invested in the index on the session's first date and each later capital increase as invested on its effective date, each held thereafter and valued forward by the index's price movement, and these per-session positions are summed on the common date axis. Consequently the benchmark line starts from zero before any selected session has opened and **steps up as each selected session opens** (and on each later capital increase), mirroring how the combined equity line aggregates, so the two curves are directly comparable in USD (no percent/dollar toggle). A selected benchmark that has no price data over the range SHALL draw no line, and its legend control SHALL be inert rather than erroring. Benchmark lines SHALL be visually distinguishable from the portfolio line and from one another. Toggling a benchmark SHALL add or remove its line without issuing a new request, and changing the session selection SHALL re-aggregate the benchmark lines over the newly selected sessions. When no session is selected, no benchmark lines SHALL be drawn (the empty state is shown instead).

When the equity curve plots a line, it SHALL support **hover inspection**: moving the pointer over the plot area SHALL identify the plotted point nearest the pointer's horizontal position and SHALL show a tooltip reporting that point's **date**, the **summed equity value** in USD at that point, and the aggregated USD value of each currently-drawn benchmark line at that point. The tooltip SHALL be rendered legibly (not distorted by the chart's scaling) and SHALL be positioned near the hovered point without being clipped out of the chart area. The chart MAY also mark the hovered point visually. When the pointer leaves the plot area, the tooltip SHALL be dismissed. Hover inspection SHALL NOT change any plotted value and SHALL NOT appear when the empty state is shown.

#### Scenario: Summed line over selected sessions

- **WHEN** the Dashboard renders the equity curve with one or more sessions selected
- **THEN** it SHALL plot a single line equal to the sum of the selected sessions' values across the range, each session contributing zero before its first recorded value

#### Scenario: Toggling a session re-aggregates without refetch

- **WHEN** a user includes or excludes a session in the equity curve
- **THEN** the line, hero tiles, and leaderboard SHALL recompute from already-fetched data without a new request per toggle

#### Scenario: Benchmark legend defaults to S&P 500

- **WHEN** the Dashboard first renders the equity curve
- **THEN** it SHALL list every catalog benchmark in the legend with only the S&P 500 selected, and draw the S&P 500 line as the sum over the selected sessions of a buy-and-hold of each session's contributed capital in the S&P 500, stepping up as each selected session opens, alongside the portfolio line

#### Scenario: Toggling a benchmark adds or removes its line without refetch

- **WHEN** a user selects or deselects a benchmark in the legend
- **THEN** the chart SHALL add or remove that index's aggregated line using already-fetched data, without issuing a new request

#### Scenario: Benchmark lines re-rebase when the session selection changes

- **WHEN** a user changes which sessions are selected
- **THEN** each drawn benchmark line SHALL re-aggregate over the newly selected sessions, so excluding a session removes its contributed capital from the benchmark line just as it is removed from the equity line

#### Scenario: Benchmark without data over the range

- **WHEN** a selected benchmark has no price data over the selected range
- **THEN** the chart SHALL draw no line for it and its legend control SHALL be inert rather than erroring

#### Scenario: Hover reveals the summed value and date

- **WHEN** a user moves the pointer over the rendered combined equity curve
- **THEN** the view SHALL show a tooltip reporting the nearest point's date, the summed equity value in USD, and the aggregated USD value of each currently-drawn benchmark line at that point

#### Scenario: Tooltip dismisses on leave

- **WHEN** the pointer leaves the equity curve's plot area
- **THEN** the view SHALL dismiss the hover tooltip

#### Scenario: No sessions selected

- **WHEN** no session is selected
- **THEN** the equity curve SHALL show an empty state rather than a line, and SHALL draw no benchmark lines

### Requirement: Dashboard portfolio leaderboard

The Dashboard SHALL present a leaderboard table of the selected active sessions, sorted by return over the selected range in descending order (best first). Each row SHALL show the portfolio's name, current value, range realised profit/loss, range unrealised profit/loss, range return, and range fees, using the same money-weighted basis as the hero tiles, and SHALL link to that session's detail view. The current value column SHALL be marked as a point-in-time/live figure, and the range-scoped columns (realised profit/loss, unrealised profit/loss, return, and fees) SHALL be visually grouped under an indication of the active range, so the user can tell the point-in-time value apart from the range-scoped figures. Return direction and the realised and unrealised profit/loss SHALL be visually distinguished by sign (for example gains and losses colored differently). Deselecting a session in the equity curve SHALL remove it from the leaderboard.

#### Scenario: Sessions ranked by range return

- **WHEN** the Dashboard renders the leaderboard for a range
- **THEN** it SHALL list the selected sessions sorted by range return descending, each row showing name, value, range realised profit/loss, range unrealised profit/loss, range return, and range fees, and linking to that session's detail view

#### Scenario: Leaderboard distinguishes point-in-time value from range columns

- **WHEN** the Dashboard renders the leaderboard
- **THEN** the current value column SHALL be marked as a point-in-time/live figure and the realised, unrealised, return, and fees columns SHALL be grouped under an indication of the active range

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

The Dashboard SHALL present a universe section with a range-independent balance summary and range-dependent performers. The balance summary SHALL show the eligible versus ineligible split, the number of sectors represented, the largest sector's share, and the largest category's share, and SHALL be marked as reflecting the current composition rather than the selected range. The performers SHALL show the best and worst tracked assets by market return over the selected range, and SHALL carry an indication of the active range so that, within the one section, the user can see the balance summary does not change with the range while the performers do.

#### Scenario: Balance summary and performers shown

- **WHEN** the Dashboard renders the universe section
- **THEN** it SHALL show the current eligibility split, sectors represented, and largest sector and category shares, alongside the best and worst tracked assets by market return over the selected range

#### Scenario: Performers follow the range

- **WHEN** a user changes the selected range
- **THEN** the best/worst performers SHALL update to that range while the balance summary stays unchanged

#### Scenario: Section distinguishes current-composition balance from range-scoped performers

- **WHEN** the Dashboard renders the universe section
- **THEN** the balance summary SHALL be marked as current composition and the best/worst performers SHALL carry an indication of the active range, so the differing scopes within the one section are evident

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

### Requirement: Asset universe AI evaluation panel

The Assets page SHALL render an AI universe evaluation panel directly below the
asset-composition donut charts. The panel SHALL show the evaluation's markdown
narrative and its bulleted key findings together with the time it was generated,
SHALL display a clear outdated warning when the universe has changed since the
evaluation was generated, and SHALL provide a refresh control that regenerates the
evaluation. When no evaluation exists yet, the panel SHALL trigger generation on
first load and show a generating state until it completes.

The panel SHALL be collapsible. Its header (title, subtitle, and refresh control)
SHALL remain visible when collapsed, and a disclosure toggle SHALL show or hide the
panel body (the narrative, key findings, generation time, and the
outdated/generating/error/empty states). The panel SHALL default to expanded, and
the disclosure toggle SHALL expose its expanded or collapsed state to assistive
technology.

#### Scenario: Panel renders the evaluation under the donuts

- **WHEN** the Assets page loads and a current evaluation exists
- **THEN** a panel below the composition donuts shows the narrative, the key
  findings, and the time the evaluation was generated

#### Scenario: Outdated warning

- **WHEN** the current evaluation is reported as outdated
- **THEN** the panel displays a warning that the asset universe has changed since
  the evaluation was generated

#### Scenario: No warning when current

- **WHEN** the current evaluation is not outdated
- **THEN** the panel shows no outdated warning

#### Scenario: Manual refresh

- **WHEN** the operator activates the refresh control
- **THEN** the panel regenerates the evaluation, shows a loading state while it runs
  with the control disabled, and replaces the displayed evaluation when it completes

#### Scenario: First-load generation when empty

- **WHEN** the Assets page loads and no evaluation has ever been generated
- **THEN** the panel triggers generation and shows a generating state until the
  evaluation is available

#### Scenario: Body expanded by default

- **WHEN** the Assets page loads and the evaluation panel renders
- **THEN** the panel body is visible and the disclosure toggle reports an expanded
  state

#### Scenario: Collapse hides the body

- **WHEN** the operator activates the disclosure toggle while the panel is expanded
- **THEN** the panel body is hidden, the header and refresh control remain visible,
  and the toggle reports a collapsed state

#### Scenario: Expand shows the body again

- **WHEN** the operator activates the disclosure toggle while the panel is collapsed
- **THEN** the panel body is shown again and the toggle reports an expanded state

### Requirement: Live auto-refresh of portfolio value and P&L

The Dashboard overview, the Portfolios list, and a paper-trading session's detail performance KPIs SHALL auto-refresh their marked-to-market figures — current portfolio value, realised profit/loss, and unrealised profit/loss — on a recurring interval of approximately 30 seconds while the view is visible, so the figures track live quotes without a manual page reload. The recurring refresh SHALL pause while the view is not the active/foreground tab and SHALL resume when it becomes active again. The refresh SHALL update values in place without resetting the user's current range selection, portfolio selection, table paging, or scroll position, and SHALL NOT change the meaning of any figure — only its freshness. This auto-refresh is independent of, and additive to, the session detail's existing order-state reconciliation polling (which keys off non-terminal order statuses).

#### Scenario: Dashboard refreshes on an interval

- **WHEN** a user leaves the Dashboard open with the tab focused
- **THEN** the Dashboard SHALL re-fetch and update its current value and range profit/loss figures on a recurring ~30-second interval without a manual reload, preserving the selected range and portfolio selection

#### Scenario: Portfolios list refreshes on an interval

- **WHEN** a user leaves the Portfolios list open with the tab focused
- **THEN** the list SHALL re-fetch and update each row's current value, realised profit/loss, and unrealised profit/loss on a recurring ~30-second interval without a manual reload, preserving table paging

#### Scenario: Session detail KPIs refresh on an interval

- **WHEN** a user leaves a session's detail view open with the tab focused
- **THEN** the session's performance KPI tiles SHALL re-fetch and update their marked-to-market figures on a recurring ~30-second interval without a manual reload

#### Scenario: Refresh pauses when the view is backgrounded

- **WHEN** the tab showing the Dashboard, Portfolios list, or session detail is not the active foreground tab
- **THEN** the recurring auto-refresh SHALL pause and SHALL resume when the tab becomes active again

### Requirement: Dashboard figure-scope legibility

The Dashboard SHALL make visually clear, for every figure it presents, whether that figure is scoped to the selected range or is a point-in-time/current figure that does not change with the range, so a user understands why some numbers move when the range selector changes and others do not. The Dashboard SHALL organise its figures into three scopes and signal each scope to the user:

- **Range-scoped** figures — the aggregate and per-session realised profit/loss, unrealised profit/loss, return, and fees; the combined equity curve; the automation failed-run count; the recent-activity feed; and the universe best/worst performers — SHALL be presented grouped with the range-scoped performance region and SHALL carry an indication of the active range they cover.
- The **point-in-time current portfolio value** (net asset value) SHALL be presented separately from the range-scoped performance figures and marked as a current, live figure (as of now), consistent with the live-data indicator used elsewhere in the application.
- The **current-composition** universe balance summary (asset counts, eligible-versus-ineligible split, sectors represented, largest sector share, and largest category share) SHALL be marked as reflecting the current composition rather than the selected range.

The range selector SHALL be presented in association with the range-scoped performance region so that its governance over the range-scoped figures is evident, rather than implying it governs the point-in-time current value or the current-composition universe balance. Because the universe section mixes scopes — its balance summary is range-independent while its best/worst performers are range-scoped — the performers SHALL carry their own range indication even when shown alongside the range-independent balance summary.

#### Scenario: Range-scoped figures indicate the active range

- **WHEN** the Dashboard renders its range-scoped performance figures for a selected range
- **THEN** those figures SHALL be grouped together and SHALL carry an indication of the active range they cover

#### Scenario: Current value marked as point-in-time

- **WHEN** the Dashboard renders the aggregate current portfolio value
- **THEN** it SHALL be shown separately from the range-scoped performance figures and marked as a current/live figure that does not change with the range

#### Scenario: Universe balance marked as current composition

- **WHEN** the Dashboard renders the universe balance summary
- **THEN** it SHALL be marked as reflecting the current composition rather than the selected range

#### Scenario: Universe performers indicate the range within the composition section

- **WHEN** the Dashboard renders the universe best/worst performers alongside the range-independent balance summary
- **THEN** the performers SHALL carry their own indication of the active range, distinct from the current-composition balance summary

#### Scenario: Range selector reads as governing the performance figures

- **WHEN** the Dashboard renders the range selector
- **THEN** it SHALL be presented in association with the range-scoped performance region so a user can tell it governs the range-scoped figures and not the point-in-time current value or the current-composition universe balance

### Requirement: Session AI cost KPI tile

The session-detail performance KPI group SHALL include an "AI cost" tile that displays the session's cumulative AI cost in US dollars. When no cost value is available (the cost source is unconfigured, errored, or the session has no attributed spend), the tile SHALL render a neutral placeholder rather than a zero or an error.

#### Scenario: Tile shows the cost when available

- **WHEN** the session KPIs include an AI cost value
- **THEN** the session-detail page shows an "AI cost" tile formatted as a USD amount

#### Scenario: Tile shows a placeholder when the cost is unavailable

- **WHEN** the session KPIs carry no AI cost value
- **THEN** the "AI cost" tile renders a neutral placeholder (an em dash), not `$0.00` or an error

### Requirement: Recommendation run model selection

The recommend (universe) and watchlist run-create forms SHALL let a user choose
the AI model for the run from the shared model catalog, defaulting the selection
to the configured default recommender model. The recommendation run detail/list
SHALL display the model each run used.

#### Scenario: Form offers a model selector defaulted to the configured model

- **WHEN** a user opens the recommend or watchlist run-create form
- **THEN** it SHALL present a model selector populated from the model catalog with
  the configured default recommender model pre-selected

#### Scenario: Selected model is submitted with the run

- **WHEN** a user picks a model and starts the run
- **THEN** the run SHALL be created with that model

#### Scenario: Run displays the model it used

- **WHEN** a user views a recommendation run in the list or detail view
- **THEN** the UI SHALL show the model that run used
