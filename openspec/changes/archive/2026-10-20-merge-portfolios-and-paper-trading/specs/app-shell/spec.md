## MODIFIED Requirements

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

### Requirement: Portfolio and paper-trading views

The system SHALL provide a single unified **Portfolios** area — one list view and one per-session detail view — replacing the previously separate portfolio and paper-trading views. The unified list SHALL be session-driven: each row is a paper-trading session, and the list SHALL present, alongside each session's status, allocated capital, trade count, and profit/loss, the portfolio-definition attributes of the session's portfolio — its risk profile and its number of holdings. The list SHALL show the AI portfolio build form and the multi-session performance-comparison chart above the table. Opening a row SHALL navigate to the session's detail view at `/portfolios/:id`, where the identifier is the session's id. The session list and the session detail header SHALL identify each session by its portfolio name as the primary label, and SHALL present the strategy as secondary context rather than the primary identifier. When a session has no resolvable portfolio name, the UI SHALL fall back to the strategy label. The session detail view SHALL display its trades, runs, positions, and AI-portfolio events. The session detail view SHALL additionally display the session's **portfolio definition**, resolved via the session's portfolio reference: an overview of the portfolio's source, risk profile, maximum allocation, number of holdings, creation time, and source run, together with a holdings list whose tickers each link to the asset's detail view; when the session has no resolvable portfolio, the detail view SHALL still render the session content and SHALL omit the portfolio-definition section rather than erroring. The session detail view SHALL display the session's **AI model** — the model its AI runs execute on, shown by its catalog display name. The session detail view SHALL display the session's **automatic stop-loss configuration** — whether it is enabled and, when enabled, its threshold percentage. The session detail view SHALL display the session's **risk-guardrail configuration** — whether the guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage. The session detail view SHALL display the session's **learning-feedback configuration** — whether learning feedback (informing the rebalance agent of the session's recent prior-run outcomes) is enabled and, when enabled, its learning window (number of recent days). The session detail view SHALL display the session's **company-fundamentals configuration** — whether company fundamentals (supplying the rebalance agent with per-ticker company financials) are enabled. The session detail view SHALL display the session's **watchlist-inclusion configuration** — whether the candidate universe the AI picks from includes the user's watchlist-membership assets. Among the session's trades and runs, those produced by the automatic stop-loss SHALL be identifiable as stop-loss activity (rather than AI-driven build or rebalance activity). On the session detail view, a run that was produced by an AI build or rebalance SHALL link to that run's detail view; a run not backed by an AI-portfolio event SHALL remain non-interactive. The legacy `/paper-trading` and `/paper-trading/:id` paths SHALL redirect to `/portfolios` and `/portfolios/:id` respectively, preserving the identifier, so existing links continue to work.

On the session detail view, each of the four tables — AI-portfolio events, trades, closed positions, and runs — SHALL show one fixed-size page of rows at a time rather than a single unbounded list, with the first page showing the most recent rows. The default page size SHALL be 5 rows for the AI-portfolio events and runs tables and 10 rows for the trades and closed-positions tables. Each table SHALL provide page-through navigation (moving to the previous and next page, without infinite scroll) and SHALL indicate the user's position within the whole (for example, the current page relative to the total number of pages or rows). When a table has no more than one page of rows, its navigation SHALL convey that there are no further pages. Paging one table SHALL NOT change the page shown by the other tables.

#### Scenario: Inspect a paper-trading session

- **WHEN** a user opens a paper-trading session
- **THEN** the UI SHALL display its trades, runs, positions, and the AI decision events for that session

#### Scenario: Single unified Portfolios list

- **WHEN** a user opens the Portfolios area
- **THEN** the UI SHALL show one session-driven list of the user's portfolios (one row per paper-trading session) rather than separate portfolio and paper-trading lists

#### Scenario: List shows portfolio definition alongside performance

- **WHEN** a user views the unified Portfolios list
- **THEN** each row SHALL show the session's status, allocated capital, trade count, and profit/loss together with the portfolio's risk profile and its number of holdings

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
