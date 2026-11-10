## ADDED Requirements

### Requirement: Bot session-detail Sharpe KPI tile

The bot session-detail page SHALL display a **Sharpe ratio** KPI tile alongside the
existing bot KPI tiles, rendering the value from the bot session's KPI read. When the
Sharpe ratio is reported as unavailable (because the session lacks sufficient history),
the tile SHALL show a clear "not yet available" state with a brief explanatory hint
instead of a numeric value, consistent with how the AI paper-trading session-detail page
renders its Sharpe tile. This tile SHALL appear on the bot session-detail page only and
SHALL NOT be added to the Dashboard leaderboard or the bot list view.

#### Scenario: Sharpe tile shown on the bot detail page

- **WHEN** a user views the detail page for a bot session whose KPI read returns a Sharpe
  ratio value
- **THEN** the view SHALL display a Sharpe ratio tile using that value

#### Scenario: Sharpe not yet available on the bot detail page

- **WHEN** a user views the bot detail page for a session whose KPI read reports the
  Sharpe ratio as unavailable
- **THEN** the Sharpe tile SHALL show a "not yet available" state with a brief hint
  instead of a numeric value
