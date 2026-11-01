## MODIFIED Requirements

### Requirement: Portfolio and paper-trading views

The system SHALL provide a single unified **Portfolios** area — one list view and one per-session detail view — replacing the previously separate portfolio and paper-trading views. The unified list SHALL be session-driven: each row is a paper-trading session, and the list SHALL present, alongside each session's status, allocated capital, trade count, current portfolio value, realised profit/loss, unrealised profit/loss, and **portfolio age** (how long the session has been running, derived from the session's creation time and rendered as a compact human-readable duration, with the exact creation date available on hover), the portfolio-definition attributes of the session's portfolio — its risk profile and its number of holdings. The list's per-row current portfolio value, realised profit/loss, and unrealised profit/loss SHALL be marked to market from live quotes on an all-time basis, using the same definition of the three figures as the session detail view's performance KPIs (current value is the net asset value net of fees, realised profit/loss is the cumulative closed-lot realised profit/loss, and unrealised profit/loss is the current mark-to-market gain or loss on open positions). The list SHALL show the AI portfolio build form and the multi-session performance-comparison chart above the table. Opening a row SHALL navigate to the session's detail view at `/portfolios/:id`, where the identifier is the session's id. The session list and the session detail header SHALL identify each session by its portfolio name as the primary label, and SHALL present the strategy as secondary context rather than the primary identifier. When a session has no resolvable portfolio name, the UI SHALL fall back to the strategy label. The session detail view SHALL display its trades, runs, positions, and AI-portfolio events. The session detail view SHALL additionally display the session's **portfolio definition**, resolved via the session's portfolio reference: an overview of the portfolio's source, risk profile, maximum allocation, number of holdings, creation time, and source run, together with a holdings list whose tickers each link to the asset's detail view; when the session has no resolvable portfolio, the detail view SHALL still render the session content and SHALL omit the portfolio-definition section rather than erroring. The session detail view SHALL display the session's **AI model** — the model its AI runs execute on, shown by its catalog display name. The session detail view SHALL display the session's **automatic stop-loss configuration** — whether it is enabled and, when enabled, its threshold percentage. The session detail view SHALL display the session's **risk-guardrail configuration** — whether the guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage. The session detail view SHALL display the session's **learning-feedback configuration** — whether learning feedback (informing the rebalance agent of the session's recent prior-run outcomes) is enabled and, when enabled, its learning window (number of recent days). The session detail view SHALL display the session's **company-fundamentals configuration** — whether company fundamentals (supplying the rebalance agent with per-ticker company financials) are enabled. The session detail view SHALL display the session's **price-ML configuration** — whether the price-ML signal (supplying the rebalance agent with a per-ticker learned price-direction estimate) is enabled. The session detail view SHALL display the session's **watchlist-inclusion configuration** — whether the candidate universe the AI picks from includes the user's watchlist-membership assets. The session detail view SHALL display the session's **technical-indicator configuration** — whether the technical-indicator trend strategy (restricting entries to assets in a confirmed uptrend and attaching trend context to holdings on the build and every rebalance) is enabled. Among the session's trades and runs, those produced by the automatic stop-loss SHALL be identifiable as stop-loss activity (rather than AI-driven build or rebalance activity). On the session detail view, a run that was produced by an AI build or rebalance SHALL link to that run's detail view; a run not backed by an AI-portfolio event SHALL remain non-interactive. The legacy `/paper-trading` and `/paper-trading/:id` paths SHALL redirect to `/portfolios` and `/portfolios/:id` respectively, preserving the identifier, so existing links continue to work.

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

#### Scenario: List shows portfolio age

- **WHEN** a user views the unified Portfolios list
- **THEN** each row SHALL show the session's portfolio age — a compact human-readable duration since the session was created (for example `5d`, `3w`, `2mo`, or `1y`) — with the session's exact creation date available on hover

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

#### Scenario: Session shows its price-ML configuration

- **WHEN** a user opens a session's detail view
- **THEN** the UI SHALL indicate whether the price-ML signal is enabled for that session

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

### Requirement: AI build form asset scope and default capital

The AI portfolio build form SHALL be opened from a control on the Portfolios page and presented in a modal dialog rather than rendered inline on the page, so the page is not cluttered by the form when the user is not building a portfolio; the modal SHALL be dismissible via an explicit close control, a click on the backdrop, and the Escape key. The build form SHALL NOT offer a choice to disable rebalancing entirely — every AI portfolio is enrolled in rebalancing automatically — but SHALL present the **rebalance cadence** as a radio group of exactly three options — daily, weekly, and monthly — from which the user MUST select exactly one before the form can be submitted; the form SHALL NOT pre-select a cadence on the user's behalf, and SHALL prevent submission until a cadence is chosen, then SHALL send the chosen cadence with the build request so the resulting session is rebalanced at that cadence. The AI portfolio build form SHALL let the user choose the portfolio's asset scope — stocks only, crypto only, or both — defaulting to both, and SHALL let the user choose the session's benchmark from the fixed benchmark catalog, defaulting to S&P 500. The form SHALL also let the user choose the session's **AI model** from the fixed model catalog, defaulting to the configured default model. The form SHALL also let the user opt the portfolio into the **technical-indicator trend strategy** via a toggle that defaults to **off**. The form SHALL also let the user opt the portfolio into **company fundamentals** via a toggle that defaults to **off**, which when enabled supplies the session's rebalance agent with per-ticker company financials. The form SHALL also let the user opt the portfolio into the **price-ML signal** via a toggle that defaults to **off**, which when enabled supplies the session's rebalance agent with a per-ticker learned price-direction estimate. The form SHALL also let the user opt the portfolio into **including watchlist assets** via a toggle that defaults to **off**, which when enabled adds the user's watchlist-membership assets to the candidate universe the session's AI picks from. The form SHALL also let the user opt the portfolio into an **automatic hard stop-loss** via a toggle that defaults to **off**, and SHALL let the user set the **stop-loss threshold percentage** (defaulting to the configured default) that applies when the stop-loss is enabled; the threshold control MAY be hidden or disabled while the stop-loss toggle is off. The form SHALL also let the user opt the portfolio into **portfolio risk guardrails** via a toggle that defaults to **off**, and SHALL let the user set the guardrail parameters that apply when the guardrails are enabled — the **maximum percentage per asset**, the **maximum percentage per asset class**, the **minimum number of positions**, and the **maximum invested percentage** (cash buffer) — each defaulting to its configured default; the guardrail parameter controls MAY be hidden or disabled while the guardrail toggle is off. The form SHALL also let the user opt the portfolio into **learning feedback** via a toggle that defaults to **off**, which when enabled informs the session's rebalance agent of its own recent prior-run outcomes, and SHALL let the user set the **learning window** (number of recent days, defaulting to the configured default) that applies when learning feedback is enabled; the window control MAY be hidden or disabled while the learning-feedback toggle is off. The form's allocated-capital input SHALL default to the configured default amount (10,000). The chosen asset scope SHALL be sent with the build request so the resulting portfolio is restricted to the selected asset types, the chosen benchmark SHALL be sent with the build request so the session is compared against it, the chosen model SHALL be sent with the build request so the session's AI runs execute on it, the technical-indicator opt-in SHALL be sent with the build request so the resulting session applies (or omits) the trend strategy accordingly, the company-fundamentals opt-in SHALL be sent with the build request so the resulting session enables (or omits) the fundamentals block accordingly, the price-ML opt-in SHALL be sent with the build request so the resulting session enables (or omits) the price-ML block accordingly, the watchlist-inclusion opt-in SHALL be sent with the build request so the resulting session includes (or omits) watchlist assets in its candidate universe accordingly, the stop-loss opt-in and (when enabled) threshold SHALL be sent with the build request so the resulting session applies (or omits) the automatic stop-loss accordingly, and the risk-guardrail opt-in and (when enabled) its parameters SHALL be sent with the build request so the resulting session applies (or omits) the guardrails accordingly, and the learning-feedback opt-in and (when enabled) its window SHALL be sent with the build request so the resulting session enables (or omits) learning feedback accordingly.

#### Scenario: Opening the build form opens a modal

- **WHEN** a user activates the "Build an AI portfolio" control on the Portfolios page
- **THEN** the build form SHALL be presented in a modal dialog overlaying the page rather than inline

#### Scenario: Dismissing the build modal

- **WHEN** the build modal is open and the user activates its close control, clicks the backdrop, or presses the Escape key
- **THEN** the modal SHALL be dismissed and the Portfolios page SHALL be shown without the form

#### Scenario: Form offers no daily-rebalancing choice

- **WHEN** a user opens the AI portfolio build form
- **THEN** the form SHALL NOT present any control to disable rebalancing, and SHALL present a rebalance-cadence radio group of daily, weekly, and monthly from which exactly one must be selected, whose value is sent with the build request

#### Scenario: Default form values

- **WHEN** a user opens the AI portfolio build form
- **THEN** the capital input SHALL default to 10,000, the asset scope SHALL default to both (stocks and crypto), the benchmark SHALL default to S&P 500, the model SHALL default to the configured default model, the technical-indicator trend-strategy toggle SHALL default to off, the company-fundamentals toggle SHALL default to off, the price-ML toggle SHALL default to off, the include-watchlist-assets toggle SHALL default to off, the automatic stop-loss toggle SHALL default to off, the risk-guardrails toggle SHALL default to off, the learning-feedback toggle SHALL default to off, and the learning-window control SHALL default to the configured default, and the rebalance-cadence radio group SHALL have no option pre-selected

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

#### Scenario: Opting into the price-ML signal

- **WHEN** a user enables the price-ML toggle and submits the build form
- **THEN** the UI SHALL send the price-ML opt-in with the build request so the resulting session supplies the price-ML block to its rebalance agent

#### Scenario: Leaving the price-ML signal off

- **WHEN** a user submits the build form without enabling the price-ML toggle
- **THEN** the UI SHALL send the build request with the price-ML opt-in off so the resulting session supplies no price-ML block

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

#### Scenario: Selecting a rebalance cadence

- **WHEN** a user selects one of the daily, weekly, or monthly cadence radio options and submits the build form
- **THEN** the UI SHALL send the selected cadence with the build request

#### Scenario: Cadence selection is required to submit

- **WHEN** a user attempts to submit the build form without having selected a rebalance cadence
- **THEN** the form SHALL prevent submission until the user selects exactly one cadence
