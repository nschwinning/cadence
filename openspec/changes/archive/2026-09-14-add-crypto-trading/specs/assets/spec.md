## ADDED Requirements

### Requirement: Crypto assets are a first-class, tradable universe member

The system SHALL allow crypto assets to be added to the universe and SHALL classify
them as crypto from the market-data provider's instrument type. A crypto asset's
missing equity-only attributes (such as sector) SHALL be a valid state and SHALL NOT
prevent it from being added or traded. Eligibility SHALL remain informational and
SHALL NOT be a precondition for the AI to trade a universe asset.

#### Scenario: Add a crypto asset

- **WHEN** a client adds a crypto ticker (e.g. `BTC-USD`) that the provider reports
  as a cryptocurrency
- **THEN** the system SHALL store it in the universe classified as crypto, with a
  null sector treated as valid

#### Scenario: Crypto included as a trading candidate

- **WHEN** the AI build or rebalance reads the asset universe
- **THEN** crypto assets SHALL be presented as candidates alongside equities,
  regardless of their eligibility flag
