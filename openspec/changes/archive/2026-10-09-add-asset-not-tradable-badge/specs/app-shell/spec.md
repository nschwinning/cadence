## MODIFIED Requirements

### Requirement: Asset management views

The system SHALL provide a view to add an asset, browse the paginated/searchable/filterable asset list, and open an asset's detail (including its recent price history and profile). Errors from the API (duplicate, unknown ticker, data unavailable) SHALL be surfaced to the user with a meaningful message. In the asset list, each asset that is not tradable on Alpaca — a foreign or otherwise unpriceable listing, identified by the absence of a resolved Alpaca symbol — SHALL be visually flagged as not tradable, distinct from the asset's eligibility status; assets that are tradable on Alpaca SHALL NOT carry that flag.

#### Scenario: Add and browse assets

- **WHEN** a user adds a ticker and browses the list
- **THEN** the newly added asset SHALL appear in the list and be openable in a detail view

#### Scenario: Add error surfaced

- **WHEN** adding a ticker returns a duplicate/unknown/unavailable error
- **THEN** the UI SHALL display a corresponding message and remain usable

#### Scenario: Not-tradable asset is flagged in the list

- **WHEN** a user browses the asset list and an asset has no resolved Alpaca symbol (a foreign or unpriceable listing)
- **THEN** the UI SHALL show a not-tradable indicator on that asset's row, separate from its eligibility status, that explains the asset cannot be traded on Alpaca and should be replaced with a tradable US listing

#### Scenario: Tradable asset is not flagged

- **WHEN** a user browses the asset list and an asset has a resolved Alpaca symbol
- **THEN** the UI SHALL NOT show the not-tradable indicator on that asset's row
