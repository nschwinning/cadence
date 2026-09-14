## ADDED Requirements

### Requirement: Trade both equities and crypto assets

The system SHALL determine each asset's class (equity or crypto) from its stored
asset record and route brokerage calls accordingly. For crypto it SHALL translate
symbols between the universe's canonical format (e.g. `BTC-USD`) and the brokerage
format (e.g. `BTC/USD`) at the brokerage boundary, submit orders with a
crypto-compatible time-in-force and fractional quantities, and read quotes from the
brokerage's crypto market-data endpoints. Positions returned by the brokerage SHALL
be reconciled back to canonical universe tickers. Equity routing SHALL be unchanged.

#### Scenario: Crypto order routing

- **WHEN** the executor places an order for an asset classified as crypto
- **THEN** the system SHALL send the brokerage-format crypto symbol with a
  crypto-compatible time-in-force and a fractional quantity, not an equities-style
  whole-share day order

#### Scenario: Crypto quote routing

- **WHEN** the executor requests a quote for a crypto asset
- **THEN** the system SHALL obtain the price from the brokerage's crypto market-data
  endpoint rather than the equities endpoint

#### Scenario: Position reconciliation

- **WHEN** the brokerage reports a crypto position in its own symbol format
- **THEN** the system SHALL map it to the canonical universe ticker so it matches
  the portfolio's holdings during rebalance

### Requirement: Fractional sizing for crypto

The system SHALL size crypto positions as fractional units of the asset, skipping a
position only when its value falls below the brokerage's minimum tradable notional.
Equity positions SHALL continue to be sized in whole shares, skipping allocations
smaller than one share.

#### Scenario: Fractional crypto position

- **WHEN** a crypto allocation buys less than one whole unit at the current price
- **THEN** the system SHALL place a fractional-unit order rather than skipping it

#### Scenario: Below minimum notional

- **WHEN** a crypto allocation's value is below the brokerage minimum notional
- **THEN** the system SHALL skip that position without failing the run and record it
  as not executed

### Requirement: Rebalance crypto around the clock

Because crypto trades 24/7, the daily rebalance SHALL execute crypto trades even
when the equities market is closed. When the equities market is closed, the system
SHALL still rebalance crypto holdings and targets and SHALL skip only the equity
orders. The system SHALL record the run as skipped (no orders) only when nothing is
tradable — that is, the equities market is closed and neither the current positions
nor the targets include any crypto.

#### Scenario: Crypto rebalances while equities market is closed

- **WHEN** a daily rebalance runs while the equities market is closed and the
  session holds or targets crypto
- **THEN** the system SHALL trade the crypto toward its targets and skip equity
  orders, recording the run as executed rather than skipped

#### Scenario: Nothing tradable while closed

- **WHEN** a daily rebalance runs while the equities market is closed and neither
  the positions nor the targets include any crypto
- **THEN** the system SHALL record a skipped run and mark the rebalance event
  skipped
