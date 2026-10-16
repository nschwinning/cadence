## MODIFIED Requirements

### Requirement: View asset detail with a daily snapshot

The system SHALL provide detail for a single asset by ticker, including a cached once-per-day snapshot (current price, previous close, short description, volume figures, and a recent close-price history). At most one snapshot SHALL exist per asset per calendar day; concurrent detail requests on the same day SHALL converge on a single snapshot. The detail response SHALL also include the asset's available SEC EDGAR fundamentals when a fundamentals record exists for the asset, and SHALL report fundamentals as absent (null) when none has been fetched. Including fundamentals SHALL NOT trigger a fundamentals fetch and SHALL NOT fail the detail request when fundamentals are absent.

#### Scenario: Fetch detail for a known asset

- **WHEN** a client requests detail for an existing ticker
- **THEN** the system SHALL return the asset plus its snapshot for the current day, fetching and caching the snapshot if not already present

#### Scenario: Detail includes available fundamentals

- **WHEN** a client requests detail for an asset that has a stored fundamentals record
- **THEN** the system SHALL include that asset's fundamentals in the detail response

#### Scenario: Detail reports absent fundamentals

- **WHEN** a client requests detail for an asset that has no stored fundamentals record
- **THEN** the system SHALL return the detail with fundamentals reported as absent, without fetching fundamentals and without failing the request

#### Scenario: Detail for an unknown asset

- **WHEN** a client requests detail for a ticker that is not in the universe
- **THEN** the system SHALL respond 404
