## ADDED Requirements

### Requirement: Session-detail drawdown and trade-effectiveness KPI tiles

The paper-trading session-detail page SHALL display KPI tiles for the session's maximum drawdown, win rate, average win, average loss, best trade, and worst trade, alongside the existing session KPI tiles. Each tile SHALL render its metric using the value from the session KPI read, formatting maximum drawdown and win rate as percentages and the average/best/worst trade figures as currency amounts. When a metric is reported as absent, its tile SHALL render a neutral placeholder rather than a misleading numeric value. These tiles SHALL appear on the session-detail page only and SHALL NOT be added to the multi-session comparison list.

#### Scenario: Tiles show the new metrics

- **WHEN** a user views the detail page for a session whose KPI read returns maximum drawdown, win rate, and trade-effectiveness figures
- **THEN** the page SHALL display tiles for maximum drawdown and win rate as percentages and for average win, average loss, best trade, and worst trade as currency amounts

#### Scenario: Absent metric shows a placeholder

- **WHEN** a user views the detail page for a session whose KPI read reports one or more of these metrics as absent
- **THEN** each affected tile SHALL display a neutral placeholder instead of a numeric value
