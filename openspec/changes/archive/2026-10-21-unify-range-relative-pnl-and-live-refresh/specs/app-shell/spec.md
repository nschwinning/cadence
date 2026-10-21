## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Portfolio and paper-trading views

The system SHALL provide a single unified **Portfolios** area — one list view and one per-session detail view — replacing the previously separate portfolio and paper-trading views. The unified list SHALL be session-driven: each row is a paper-trading session, and the list SHALL present, alongside each session's status, allocated capital, trade count, current portfolio value, realised profit/loss, and unrealised profit/loss, the portfolio-definition attributes of the session's portfolio — its risk profile and its number of holdings. The list's per-row current portfolio value, realised profit/loss, and unrealised profit/loss SHALL be marked to market from live quotes on an all-time basis, using the same definition of the three figures as the session detail view's performance KPIs (current value is the net asset value net of fees, realised profit/loss is the cumulative closed-lot realised profit/loss, and unrealised profit/loss is the current mark-to-market gain or loss on open positions). The list SHALL show the AI portfolio build form and the multi-session performance-comparison chart above the table. Opening a row SHALL navigate to the session's detail view at `/portfolios/:id`, where the identifier is the session's id. The session list and the session detail header SHALL identify each session by its portfolio name as the primary label, and SHALL present the strategy as secondary context rather than the primary identifier. When a session has no resolvable portfolio name, the UI SHALL fall back to the strategy label. The session detail view SHALL display its trades, runs, positions, and AI-portfolio events. The session detail view SHALL additionally display the session's **portfolio definition**, resolved via the session's portfolio reference: an overview of the portfolio's source, risk profile, maximum allocation, number of holdings, creation time, and source run, together with a holdings list whose tickers each link to the asset's detail view; when the session has no resolvable portfolio, the detail view SHALL still render the session content and SHALL omit the portfolio-definition section rather than erroring. The session detail view SHALL display the session's **AI model** — the model its AI runs execute on, shown by its catalog display name. The session detail view SHALL display the session's **automatic stop-loss configuration** — whether it is enabled and, when enabled, its threshold percentage. The session detail view SHALL display the session's **risk-guardrail configuration** — whether the guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage. The session detail view SHALL display the session's **learning-feedback configuration** — whether learning feedback (informing the rebalance agent of the session's recent prior-run outcomes) is enabled and, when enabled, its learning window (number of recent days). The session detail view SHALL display the session's **company-fundamentals configuration** — whether company fundamentals (supplying the rebalance agent with per-ticker company financials) are enabled. The session detail view SHALL display the session's **watchlist-inclusion configuration** — whether the candidate universe the AI picks from includes the user's watchlist-membership assets. Among the session's trades and runs, those produced by the automatic stop-loss SHALL be identifiable as stop-loss activity (rather than AI-driven build or rebalance activity). On the session detail view, a run that was produced by an AI build or rebalance SHALL link to that run's detail view; a run not backed by an AI-portfolio event SHALL remain non-interactive. The legacy `/paper-trading` and `/paper-trading/:id` paths SHALL redirect to `/portfolios` and `/portfolios/:id` respectively, preserving the identifier, so existing links continue to work.

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

### Requirement: Dashboard global range selector

The Dashboard SHALL present a single range selector offering the choices `1D`, `1W`, `1M`, `YTD`, `1Y`, and `Max`, with one range active at a time. Changing the selected range SHALL drive every range-dependent section of the Dashboard (performance tiles, equity curve, portfolio leaderboard, automation failed-run count, recent activity, and universe performers) so that the whole view answers for the same horizon. The universe balance summary is range-independent and SHALL NOT change with the selector. The point-in-time current portfolio value is range-independent and SHALL NOT change with the selector. The range selector SHALL be presented in association with the range-scoped performance region (rather than only beside the page title) so that its scope — the range-dependent figures, not the point-in-time current value or the current-composition universe balance — is evident to the user.

#### Scenario: Selecting a range updates the whole dashboard

- **WHEN** a user selects a different range
- **THEN** the performance tiles, equity curve, leaderboard, recent activity, and universe performers SHALL all refresh to that range while the universe balance summary and the point-in-time current value stay unchanged

#### Scenario: Selector presented with the performance region

- **WHEN** the Dashboard renders the range selector
- **THEN** it SHALL be presented in association with the range-scoped performance region so its governance over the range-dependent figures is evident, rather than implying it governs the point-in-time current value or the current-composition universe balance

### Requirement: Dashboard aggregate performance tiles

The Dashboard SHALL present, for the active sessions currently selected in the equity curve, the aggregate **current portfolio value** as a point-in-time figure marked as current/live and shown separately from the range-scoped performance tiles. The Dashboard SHALL also present range-scoped performance tiles showing, over the selected range, the summed realised profit/loss, the summed unrealised profit/loss, the money-weighted return, and the fees incurred within the range, grouped together under an indication of the active range. The summed realised and unrealised tiles SHALL use the per-session range-relative realised and unrealised profit/loss summed across the selected sessions, and SHALL be visually distinguished by sign (gain versus loss). The range-scoped tiles SHALL reflect the current portfolio selection and the selected range; the current value SHALL reflect the current selection but SHALL NOT change with the range. The realised and unrealised figures are shown as two independent amounts and are not presented as an additive breakdown of the range return.

#### Scenario: Current value shown as point-in-time

- **WHEN** the Dashboard renders the aggregate performance tiles
- **THEN** the aggregate current portfolio value SHALL be shown separately from the range-scoped tiles and marked as a current/live figure that does not change when the range changes

#### Scenario: Tiles reflect range and selection

- **WHEN** a user changes the range or the set of selected portfolios
- **THEN** the range-scoped tiles SHALL recompute to show summed range realised P&L, summed range unrealised P&L, money-weighted range return, and range fees for the selected sessions, grouped under an indication of the active range

#### Scenario: Realised and unrealised tiles distinguished by sign

- **WHEN** the summed range realised or unrealised profit/loss for the selected sessions is positive or negative
- **THEN** the corresponding tile SHALL indicate the sign visually (gain versus loss)

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
