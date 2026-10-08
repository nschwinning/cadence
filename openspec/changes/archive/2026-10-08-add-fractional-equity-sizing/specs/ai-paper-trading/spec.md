## MODIFIED Requirements

### Requirement: Fractional sizing for crypto

The system SHALL size crypto positions as fractional units of the asset, skipping a
position only when its value falls below the brokerage's minimum tradable notional.
Equity sizing is governed by the "Fractional sizing for fractionable equities"
requirement.

#### Scenario: Fractional crypto position

- **WHEN** a crypto allocation buys less than one whole unit at the current price
- **THEN** the system SHALL place a fractional-unit order rather than skipping it

#### Scenario: Below minimum notional

- **WHEN** a crypto allocation's value is below the brokerage minimum notional
- **THEN** the system SHALL skip that position without failing the run and record it
  as not executed

## ADDED Requirements

### Requirement: Fractional sizing for fractionable equities

The system SHALL size an equity position in fractional shares when the asset is known
to be fractionable at the brokerage, so the position reaches its target weight without
leaving the sub-one-share remainder as idle cash. When the asset is not known to be
fractionable — including when its fractionability is unknown — the system SHALL size it
in whole shares as before. Fractional share quantities SHALL be rounded to a fixed
quantity precision. The system SHALL skip an equity allocation only when its value falls
below a configured minimum tradable notional (rather than skipping any allocation worth
less than one whole share), recording the skipped allocation as not executed without
failing the run. This applies uniformly at build, at rebalance (where the traded amount
is the signed difference between the target and current position), and at position exit.

When the system places a fractional equity order, that order SHALL use an order type and
time-in-force the brokerage accepts for fractional equity trading (a market or day-limit
order with a day time-in-force). Whole-share equity orders SHALL be unaffected.

An asset's equity fractionability SHALL be determined from the brokerage at the time the
asset is added to the universe and persisted on the asset record; assets added before
this capability existed SHALL have their fractionability backfilled from the brokerage,
and any asset whose fractionability cannot be determined SHALL be treated as
non-fractionable.

#### Scenario: Fractionable equity sized to target weight

- **WHEN** an equity allocation for a fractionable asset does not divide evenly into
  whole shares at the current price
- **THEN** the system SHALL place a fractional-share order sized to the target weight
  rather than truncating down to whole shares

#### Scenario: Non-fractionable equity stays whole-share

- **WHEN** an equity allocation is for an asset that is not fractionable (or whose
  fractionability is unknown)
- **THEN** the system SHALL size the position in whole shares, as it did before this
  capability

#### Scenario: Equity allocation below minimum notional

- **WHEN** an equity allocation's value is below the configured minimum tradable
  notional
- **THEN** the system SHALL skip that position without failing the run and record it as
  not executed, rather than skipping it on a one-share threshold

#### Scenario: Fractional equity rebalance trades the delta

- **WHEN** a rebalance changes a fractionable equity's target weight so the target
  share quantity differs from the current holding by a fractional amount above the dust
  threshold
- **THEN** the system SHALL trade the fractional difference toward the target rather
  than requiring at least a one-share change

#### Scenario: Fractional equity order uses a compatible order type

- **WHEN** the system submits a fractional equity order to the brokerage
- **THEN** the order SHALL use a market or day-limit order with a day time-in-force so
  the brokerage accepts the fractional quantity

#### Scenario: Fractionability determined at add time and backfilled

- **WHEN** an asset is added to the universe, or an asset predating this capability is
  encountered
- **THEN** the system SHALL record whether the brokerage lists the asset as fractionable
  (treating an undeterminable result as non-fractionable) and use that flag when sizing
  equity orders
