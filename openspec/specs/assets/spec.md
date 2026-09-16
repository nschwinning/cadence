# assets Specification

## Purpose
Lets a user build and curate a universe of tradeable assets sourced from public market data, with a consistent eligibility judgement, so downstream recommendation and trading features operate on a known, vetted set of instruments.

## Requirements

### Requirement: Add an asset by ticker

The system SHALL allow a client to add an asset by its ticker symbol. The system SHALL normalize the ticker (trim and uppercase), fetch market and profile data from the market-data provider, derive metrics, and evaluate eligibility before any persistence occurs. The system SHALL support only tradeable categories — **stock** and **crypto**; an asset the provider classifies as any other category (for example ETF, fund, or other) SHALL be rejected and SHALL NOT be persisted. Tradability SHALL be authoritative: before persistence the system SHALL look the asset up on the brokerage and SHALL reject it unless the brokerage lists it as tradable, and it SHALL capture the brokerage's canonical symbol and store it on the asset. If the brokerage is unconfigured or unreachable, the add SHALL fail and nothing SHALL be persisted. The stored asset SHALL include ticker, name, category, sector, exchange, currency, the brokerage's canonical symbol, profile fields, derived metrics, an eligibility flag, and the per-criterion evaluation results.

#### Scenario: Successfully add a new asset

- **WHEN** a client POSTs a valid, previously unseen ticker classified as stock or crypto that the brokerage lists as tradable
- **THEN** the system fetches its data, evaluates eligibility, stores the brokerage's canonical symbol, persists the asset, and responds 201 with the full asset record including its criteria results

#### Scenario: Unsupported category

- **WHEN** a client adds a ticker the provider classifies as a category other than stock or crypto (for example an ETF, mutual fund, or other instrument)
- **THEN** the system SHALL respond 422 naming the unsupported category and SHALL NOT persist the asset

#### Scenario: Not tradable on the brokerage

- **WHEN** a client adds a ticker of a supported category that the brokerage does not list, or lists as not tradable (for example a non-US listing such as `BAYN.DE`)
- **THEN** the system SHALL respond 422 indicating the asset is not tradable and SHALL NOT persist the asset

#### Scenario: Brokerage unavailable

- **WHEN** the brokerage is unconfigured or unreachable while adding an asset
- **THEN** the system SHALL respond 503 and SHALL NOT persist a partial record

#### Scenario: Duplicate ticker

- **WHEN** a client adds a ticker that already exists (after normalization)
- **THEN** the system SHALL NOT create a second record and SHALL respond 409

#### Scenario: Unknown ticker

- **WHEN** a client adds a ticker the provider cannot resolve to usable data
- **THEN** the system SHALL respond 422 and SHALL NOT persist a partial record

#### Scenario: Market data temporarily unavailable

- **WHEN** the market-data provider fails or times out while adding an asset
- **THEN** the system SHALL respond 503 and SHALL NOT persist a partial record

### Requirement: List assets with pagination, search, sorting, and filtering

The system SHALL return a paginated list of assets with a total count. It SHALL support a bounded page size chosen from an allowed set, an offset, a case-insensitive substring search over ticker and name, sorting by an allowed field and direction with deterministic tie-breaking, and repeatable filters by category and by sector validated against the known value sets.

#### Scenario: Default listing

- **WHEN** a client requests the asset list without parameters
- **THEN** the system SHALL return the first page of assets and the total count

#### Scenario: Search and filter

- **WHEN** a client provides a search term and one or more category/sector filters
- **THEN** the system SHALL return only assets matching the search term AND all supplied filters, with the total reflecting the filtered set

#### Scenario: Invalid pagination or sort parameter

- **WHEN** a client supplies a page size, sort field, direction, category, or sector outside the allowed set
- **THEN** the system SHALL respond with a validation error (422)

### Requirement: View asset detail with a daily snapshot

The system SHALL provide detail for a single asset by ticker, including a cached once-per-day snapshot (current price, previous close, short description, volume figures, and a recent close-price history). At most one snapshot SHALL exist per asset per calendar day; concurrent detail requests on the same day SHALL converge on a single snapshot.

#### Scenario: Fetch detail for a known asset

- **WHEN** a client requests detail for an existing ticker
- **THEN** the system SHALL return the asset plus its snapshot for the current day, fetching and caching the snapshot if not already present

#### Scenario: Detail for an unknown asset

- **WHEN** a client requests detail for a ticker that is not in the universe
- **THEN** the system SHALL respond 404

### Requirement: Delete an asset

The system SHALL allow removal of an asset by its identifier, cascading to its dependent snapshot data.

#### Scenario: Delete an existing asset

- **WHEN** a client deletes an existing asset by id
- **THEN** the system SHALL remove the asset and its snapshots and respond 204

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

### Requirement: USD-based eligibility evaluation

The system SHALL evaluate each asset against category-specific eligibility criteria expressed in USD, converting non-USD figures using a current FX rate. Equities SHALL be evaluated against minimum price, minimum average daily turnover, minimum market capitalization, and minimum available history. Crypto SHALL be evaluated against a distinct profile that OMITS the per-unit price criterion (per-unit price is not meaningful for crypto) and applies its own thresholds for average daily turnover, market capitalization, and available history; relative to equities, crypto's history threshold SHALL be shorter and its liquidity and market-capitalization floors higher. A category without a specific profile SHALL use the equity profile. The system SHALL record, per asset, each evaluated criterion's name, pass/fail outcome, observed value, and threshold, and SHALL set an overall eligibility flag that is true only when every criterion in the asset's profile passes. A missing (unresolved) metric SHALL fail its criterion. The normalized metrics the system stores and exposes for an asset (market capitalization and average daily turnover) SHALL be denominated in USD.

#### Scenario: Eligible asset

- **WHEN** an asset meets every threshold in its category's profile
- **THEN** the system SHALL mark it eligible and store each criterion result

#### Scenario: Ineligible asset

- **WHEN** an asset fails one or more thresholds in its category's profile
- **THEN** the system SHALL mark it ineligible and store the failing criterion results with observed values and thresholds

#### Scenario: Crypto is not evaluated on per-unit price

- **WHEN** a crypto asset is evaluated
- **THEN** the system SHALL NOT include a price criterion in its results, and a low per-unit price SHALL NOT by itself make the asset ineligible

#### Scenario: Crypto applies its own thresholds on shared criteria

- **WHEN** a crypto asset clears the equity market-capitalization or turnover floors but not the higher crypto floors
- **THEN** the system SHALL mark the corresponding crypto criteria as failed

#### Scenario: Non-USD figures are normalized to USD

- **WHEN** an asset reports its market data in a currency other than USD
- **THEN** the system SHALL convert its price, market capitalization, and average daily turnover to USD using a current FX rate before evaluating them against the USD thresholds
