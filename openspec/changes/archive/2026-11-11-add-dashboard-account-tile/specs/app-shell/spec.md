## ADDED Requirements

### Requirement: Dashboard broker account tile

The dashboard SHALL show a "Broker account" section containing a tile with the shared broker
account's **free capital** — the capital still available for new bots and AI portfolios —
defined as the account's cash excluding short-sale proceeds minus the cash Cadence has
committed (the committed-cash check's difference). The tile SHALL also show the committed
total and the account cash it is measured against, in the app's USD formatting, and SHALL
link to the Admin page. The tile SHALL be account-wide: it SHALL NOT react to the dashboard
range selector or to the combined-equity chart's portfolio selection. It SHALL refresh
periodically like the rest of the live dashboard figures.

The tile SHALL warn:

- with an amber "low capital" warning when free capital is positive but below $1,000, the
  smallest capital a new bot or AI portfolio can be built with;
- with a red "no capital left" warning when free capital is zero or negative, stating that new
  bots or portfolios cannot be funded;
- with a red "short positions" warning when the account holds one or more short positions,
  stating how many and their total value.

Both red warnings SHALL be shown together when both apply. When none applies the tile SHALL
show no warning. When the broker account cannot be read the tile SHALL say the broker is
unavailable instead of showing figures or warnings.

#### Scenario: Healthy account

- **WHEN** free capital is $25,000 and the account holds no short positions
- **THEN** the tile SHALL show $25,000 of free capital, the committed total and account cash,
  and no warning

#### Scenario: Low capital

- **WHEN** free capital is $600
- **THEN** the tile SHALL show an amber low-capital warning

#### Scenario: No capital left

- **WHEN** free capital is zero or negative
- **THEN** the tile SHALL show a red warning that no capital is left for new bots or
  portfolios

#### Scenario: Short positions

- **WHEN** the account holds two short positions worth $201,000 in total
- **THEN** the tile SHALL show a red warning naming two short positions and $201,000

#### Scenario: Broker unavailable

- **WHEN** the broker account cannot be read
- **THEN** the tile SHALL say the broker is unavailable and show no figures or warnings

#### Scenario: Independent of range and selection

- **WHEN** the operator changes the dashboard range or deselects portfolios in the equity chart
- **THEN** the tile's figures SHALL NOT change
