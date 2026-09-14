# dashboard Specification

## Purpose
Gives the user a single at-a-glance summary of the state of their universe, portfolios, and paper-trading activity, so the health and scale of the system is visible without navigating into each area.

## Requirements

### Requirement: Aggregated dashboard metrics

The system SHALL provide a single endpoint returning aggregated metrics across the product: the size and composition of the asset universe (for example counts by category and by sector, and eligible vs. ineligible counts), the number of portfolios, and paper-trading activity (for example the number of active sessions and recent trades). The metrics SHALL be computed from current persisted data.

#### Scenario: Fetch dashboard metrics

- **WHEN** a client requests the dashboard metrics
- **THEN** the system SHALL return the current aggregated counts across assets, portfolios, and paper-trading sessions

#### Scenario: Empty system

- **WHEN** no assets, portfolios, or sessions exist yet
- **THEN** the system SHALL return zeroed metrics rather than an error
