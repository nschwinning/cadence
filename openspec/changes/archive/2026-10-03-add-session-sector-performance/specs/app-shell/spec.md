## ADDED Requirements

### Requirement: Session-detail sector and category performance card

The paper-trading session detail view SHALL present a card showing the session's
performance attribution grouped by sector and by category, using the session's
sector/category performance breakdown. The card SHALL offer both groupings — by sector
and by category — and let the user view one at a time. For each group the card SHALL
display the group's total profit/loss as a money amount, its return as a percentage,
and a visual indication of the group's relative magnitude. Because a group's
profit/loss can be negative, the card SHALL use a sign-aware presentation (rows or
diverging bars with profit/loss distinguished by sign, consistent with the app's KPI
gain/loss styling) rather than a donut, which cannot represent negative contributions.
A group whose return is unavailable SHALL show a clear "not available" state for its
return instead of a numeric percentage. When the session has no positions to attribute,
the card SHALL show an empty state rather than an empty chart. The card SHALL reflect
the values returned by the breakdown each time the view loads.

#### Scenario: Performance card shown on the session page

- **WHEN** a user opens a paper-trading session that has positions
- **THEN** the view SHALL display a sector/category performance card listing each
  group's total P&L and return using the session's performance breakdown

#### Scenario: Switch between sector and category groupings

- **WHEN** the user toggles the card's grouping
- **THEN** the card SHALL show the performance grouped by sector or by category
  accordingly

#### Scenario: Gains and losses distinguished

- **WHEN** a group's total P&L is positive or negative
- **THEN** the card SHALL indicate the sign visually (gain versus loss), consistent with
  the app's KPI sign styling

#### Scenario: Group return unavailable

- **WHEN** a group's return is reported as unavailable
- **THEN** the card SHALL show a "not available" state for that group's return instead
  of a numeric percentage

#### Scenario: Empty state

- **WHEN** the session has no positions to attribute
- **THEN** the card SHALL show an empty state rather than an empty chart
