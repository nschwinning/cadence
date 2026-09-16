# app-shell Specification

## Purpose
Provides the web application's persistent shell and navigation so users can move between the dashboard, assets, portfolios, and paper-trading views, and interact with asynchronous AI runs through a consistent, responsive interface.

## Requirements

### Requirement: Persistent application shell

The system SHALL present a persistent shell (header and sidebar navigation with the main content area) around every page. Navigation SHALL offer entries for Dashboard, Assets, Portfolios, Paper Trading, and Runs, and SHALL indicate the active view. The shell SHALL be responsive, collapsing the sidebar on small viewports.

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

The system SHALL provide views to list portfolios and open a portfolio, and to list paper-trading sessions and open a session showing its trades, runs, positions, and AI-portfolio events.

#### Scenario: Inspect a paper-trading session

- **WHEN** a user opens a paper-trading session
- **THEN** the UI SHALL display its trades, runs, positions, and the AI decision events for that session

### Requirement: AI run history and detail views

The system SHALL provide a Runs view that lists AI runs (build and rebalance) across all sessions, newest first, showing at least each run's type, status, number of orders executed, and time, and SHALL let a user open a run to a detail view. The run detail view SHALL show the run's AI reasoning, its research (each web search's query and results), the trades the run opened, and the positions the run closed.

#### Scenario: Browse runs

- **WHEN** a user opens the Runs view
- **THEN** the UI SHALL list AI runs across all sessions newest first and allow opening any run's detail

#### Scenario: Inspect a run

- **WHEN** a user opens a run's detail
- **THEN** the UI SHALL display the run's reasoning, its research (queries and results), the trades it opened, and the positions it closed

### Requirement: Session value history chart

The paper-trading session view SHALL render a line chart of the session's total
portfolio value over time from its daily value-history snapshots. When the session
has fewer than two snapshots the view SHALL show a placeholder indicating there is
not yet enough history to chart, rather than a broken or empty chart. While the value
history is loading or fails to load, the view SHALL show a loading or error state
consistent with the page's other panels.

#### Scenario: Chart renders with history

- **WHEN** a user opens a session that has at least two value snapshots
- **THEN** the view SHALL render a line chart of the session's total value over time

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
