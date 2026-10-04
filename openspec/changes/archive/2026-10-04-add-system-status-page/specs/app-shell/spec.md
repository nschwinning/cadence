## MODIFIED Requirements

### Requirement: Persistent application shell

The system SHALL present a persistent shell (header and sidebar navigation with the main content area) around every page. Navigation SHALL offer entries for Dashboard, Assets, Portfolios, Paper Trading, Runs, and System, and SHALL indicate the active view. The shell SHALL be responsive, collapsing the sidebar on small viewports.

#### Scenario: Navigate between views

- **WHEN** a user selects a navigation entry
- **THEN** the application SHALL render that view within the shell and mark the entry active without a full page reload

#### Scenario: Small viewport

- **WHEN** the viewport is narrow
- **THEN** the sidebar SHALL collapse into a toggleable menu

## ADDED Requirements

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
