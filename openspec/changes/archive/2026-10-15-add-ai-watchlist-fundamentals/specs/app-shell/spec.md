## MODIFIED Requirements

### Requirement: Persistent application shell

The system SHALL present a persistent shell (header and sidebar navigation with the main content area) around every page. Navigation SHALL offer entries for Dashboard, Assets, Watchlist, Portfolios, Paper Trading, Runs, and System, and SHALL indicate the active view. The shell SHALL be responsive, collapsing the sidebar on small viewports.

#### Scenario: Navigate between views

- **WHEN** a user selects a navigation entry
- **THEN** the application SHALL render that view within the shell and mark the entry active without a full page reload

#### Scenario: Small viewport

- **WHEN** the viewport is narrow
- **THEN** the sidebar SHALL collapse into a toggleable menu

## ADDED Requirements

### Requirement: Watchlist view

The system SHALL provide a Watchlist view that lets the user trigger an
AI-driven watchlist recommendation run and browse the resulting watchlist
entries. Triggering a run SHALL reuse the asynchronous AI-run polling behavior
(showing the run as in-progress and updating to its terminal outcome without a
manual refresh). The view SHALL list the watchlist assets (those with
`watchlist` membership, kept separate from the universe/Assets view) and SHALL
surface each entry's available SEC EDGAR fundamentals (for example revenue,
margins, cash flow, earnings, and company details), indicating when an entry's
fundamentals are unavailable. Errors from the API SHALL be surfaced with a
meaningful message.

#### Scenario: Trigger a watchlist recommendation

- **WHEN** a user starts an AI watchlist recommendation from the Watchlist view
- **THEN** the UI SHALL show the run as in-progress and SHALL automatically
  update to its final outcome when the run reaches a terminal state

#### Scenario: Browse watchlist entries with fundamentals

- **WHEN** a user opens the Watchlist view with watchlist assets present
- **THEN** the UI SHALL list those entries and display each one's available
  fundamentals, indicating any entry whose fundamentals could not be fetched

#### Scenario: Watchlist is separate from the universe

- **WHEN** a user views the Assets (universe) list and the Watchlist view
- **THEN** watchlist assets SHALL appear only in the Watchlist view and SHALL
  NOT appear in the universe asset list
