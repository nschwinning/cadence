## ADDED Requirements

### Requirement: Session performance KPI tiles

The paper-trading session detail view SHALL present the session's live performance KPIs as headline tiles: current portfolio value, realised profit/loss, unrealised profit/loss, total return, and Sharpe ratio. The total return tile SHALL show both the absolute money amount and the percentage. Monetary profit/loss and the total return SHALL be visually distinguished by sign (gain versus loss). The Sharpe tile SHALL display a clear "not yet available" state, with a brief explanatory hint, whenever the Sharpe ratio has not yet been computed because the session lacks sufficient history. The tiles SHALL reflect the values returned by the session KPI summary each time the view loads.

#### Scenario: KPIs shown on the session page

- **WHEN** a user opens a paper-trading session
- **THEN** the view SHALL display tiles for current portfolio value, realised P&L, unrealised P&L, total return, and Sharpe ratio using the session's live KPI summary

#### Scenario: Total return shows amount and percentage

- **WHEN** the session KPI summary is displayed
- **THEN** the total return tile SHALL show the absolute money amount together with the percentage of allocated capital

#### Scenario: Gains and losses distinguished

- **WHEN** a session's realised P&L, unrealised P&L, or total return is positive or negative
- **THEN** the corresponding tile SHALL indicate the sign visually (gain versus loss)

#### Scenario: Sharpe not yet available

- **WHEN** the session KPI summary reports the Sharpe ratio as unavailable
- **THEN** the Sharpe tile SHALL show a "not yet available" state with a brief hint instead of a numeric value
