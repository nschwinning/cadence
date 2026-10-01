## ADDED Requirements

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
