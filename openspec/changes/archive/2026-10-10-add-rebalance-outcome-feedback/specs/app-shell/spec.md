## MODIFIED Requirements

### Requirement: Portfolio and paper-trading views

The system SHALL provide views to list portfolios and open a portfolio, and to list paper-trading sessions and open a session showing its trades, runs, positions, and AI-portfolio events. The session list and the session detail header SHALL identify each session by its portfolio name as the primary label, and SHALL present the strategy as secondary context rather than the primary identifier. When a session has no resolvable portfolio name, the UI SHALL fall back to the strategy label. The session detail view SHALL display the session's **automatic stop-loss configuration** — whether it is enabled and, when enabled, its threshold percentage. The session detail view SHALL display the session's **risk-guardrail configuration** — whether the guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage. The session detail view SHALL display the session's **learning-feedback configuration** — whether learning feedback (informing the rebalance agent of the session's recent prior-run outcomes) is enabled and, when enabled, its learning window (number of recent days). Among the session's trades and runs, those produced by the automatic stop-loss SHALL be identifiable as stop-loss activity (rather than AI-driven build or rebalance activity). On the session detail view, a run that was produced by an AI build or rebalance SHALL link to that run's detail view; a run not backed by an AI-portfolio event SHALL remain non-interactive.

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

#### Scenario: Session shows its learning-feedback configuration

- **WHEN** a user opens a session's detail view
- **THEN** the UI SHALL indicate whether learning feedback is enabled for that session and, when enabled, its learning window

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

The AI portfolio build form SHALL let the user choose the portfolio's asset scope — stocks only, crypto only, or both — defaulting to both, and SHALL let the user choose the session's benchmark from the fixed benchmark catalog, defaulting to S&P 500. The form SHALL also let the user opt the portfolio into the **technical-indicator trend strategy** via a toggle that defaults to **off**. The form SHALL also let the user opt the portfolio into an **automatic hard stop-loss** via a toggle that defaults to **off**, and SHALL let the user set the **stop-loss threshold percentage** (defaulting to the configured default) that applies when the stop-loss is enabled; the threshold control MAY be hidden or disabled while the stop-loss toggle is off. The form SHALL also let the user opt the portfolio into **portfolio risk guardrails** via a toggle that defaults to **off**, and SHALL let the user set the guardrail parameters that apply when the guardrails are enabled — the **maximum percentage per asset**, the **maximum percentage per asset class**, the **minimum number of positions**, and the **maximum invested percentage** (cash buffer) — each defaulting to its configured default; the guardrail parameter controls MAY be hidden or disabled while the guardrail toggle is off. The form SHALL also let the user opt the portfolio into **learning feedback** via a toggle that defaults to **off**, which when enabled informs the session's rebalance agent of its own recent prior-run outcomes, and SHALL let the user set the **learning window** (number of recent days, defaulting to the configured default) that applies when learning feedback is enabled; the window control MAY be hidden or disabled while the learning-feedback toggle is off. The form's allocated-capital input SHALL default to the configured default amount (10,000). The chosen asset scope SHALL be sent with the build request so the resulting portfolio is restricted to the selected asset types, the chosen benchmark SHALL be sent with the build request so the session is compared against it, the technical-indicator opt-in SHALL be sent with the build request so the resulting session applies (or omits) the trend strategy accordingly, the stop-loss opt-in and (when enabled) threshold SHALL be sent with the build request so the resulting session applies (or omits) the automatic stop-loss accordingly, the risk-guardrail opt-in and (when enabled) its parameters SHALL be sent with the build request so the resulting session applies (or omits) the guardrails accordingly, and the learning-feedback opt-in and (when enabled) its window SHALL be sent with the build request so the resulting session enables (or omits) learning feedback accordingly.

#### Scenario: Default form values

- **WHEN** a user opens the AI portfolio build form
- **THEN** the capital input SHALL default to 10,000, the asset scope SHALL default to both (stocks and crypto), the benchmark SHALL default to S&P 500, the technical-indicator trend-strategy toggle SHALL default to off, the automatic stop-loss toggle SHALL default to off, the risk-guardrails toggle SHALL default to off, the learning-feedback toggle SHALL default to off, and the learning-window control SHALL default to the configured default

#### Scenario: Selecting an asset scope

- **WHEN** a user selects stocks only (or crypto only) and submits the build form
- **THEN** the UI SHALL send the chosen asset scope with the build request so the resulting portfolio is restricted to the selected asset types

#### Scenario: Selecting a benchmark

- **WHEN** a user selects a benchmark from the catalog and submits the build form
- **THEN** the UI SHALL send the chosen benchmark with the build request so the session is compared against it

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

#### Scenario: Opting into learning feedback

- **WHEN** a user enables the learning-feedback toggle, sets a learning window, and submits the build form
- **THEN** the UI SHALL send the learning-feedback opt-in and the chosen window with the build request so the resulting session enables learning feedback with that window

#### Scenario: Leaving learning feedback off

- **WHEN** a user submits the build form without enabling the learning-feedback toggle
- **THEN** the UI SHALL send the build request with learning feedback off so the resulting session does not apply learning feedback
