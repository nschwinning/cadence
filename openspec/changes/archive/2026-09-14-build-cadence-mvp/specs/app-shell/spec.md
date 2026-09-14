## Purpose

Provides the web application's persistent shell and navigation so users can move between the dashboard, assets, portfolios, and paper-trading views, and interact with asynchronous AI runs through a consistent, responsive interface.

## ADDED Requirements

### Requirement: Persistent application shell

The system SHALL present a persistent shell (header and sidebar navigation with the main content area) around every page. Navigation SHALL offer entries for Dashboard, Assets, Portfolios, and Paper Trading, and SHALL indicate the active view. The shell SHALL be responsive, collapsing the sidebar on small viewports.

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
