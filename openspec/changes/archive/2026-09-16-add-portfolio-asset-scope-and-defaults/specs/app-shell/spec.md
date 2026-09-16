## ADDED Requirements

### Requirement: AI build form asset scope and default capital

The AI portfolio build form SHALL let the user choose the portfolio's asset scope — stocks only, crypto only, or both — defaulting to both. The form's allocated-capital input SHALL default to the configured default amount (10,000). The chosen asset scope SHALL be sent with the build request so the resulting portfolio is restricted to the selected asset types.

#### Scenario: Default form values

- **WHEN** a user opens the AI portfolio build form
- **THEN** the capital input SHALL default to 10,000 and the asset scope SHALL default to both (stocks and crypto)

#### Scenario: Selecting an asset scope

- **WHEN** a user selects stocks only (or crypto only) and submits the build form
- **THEN** the UI SHALL send the selected asset scope with the build request

### Requirement: Monetary values displayed in USD

The application SHALL display monetary values in US dollars (`$`), consistent with the brokerage's settlement currency, across all views (including capital amounts, P&L figures, portfolio value, and KPI tiles).

#### Scenario: Money rendered as USD

- **WHEN** the UI displays a monetary amount
- **THEN** it SHALL be formatted as US dollars with a `$` symbol rather than another currency
