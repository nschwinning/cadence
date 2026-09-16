## MODIFIED Requirements

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

### Requirement: EUR-based eligibility evaluation

The system SHALL evaluate each asset against category-specific eligibility criteria expressed in EUR, converting non-EUR figures using a current FX rate. Equities SHALL be evaluated against minimum price, minimum average daily turnover, minimum market capitalization, and minimum available history. Crypto SHALL be evaluated against a distinct profile that OMITS the per-unit price criterion (per-unit price is not meaningful for crypto) and applies its own thresholds for average daily turnover, market capitalization, and available history; relative to equities, crypto's history threshold SHALL be shorter and its liquidity and market-capitalization floors higher. A category without a specific profile SHALL use the equity profile. The system SHALL record, per asset, each evaluated criterion's name, pass/fail outcome, observed value, and threshold, and SHALL set an overall eligibility flag that is true only when every criterion in the asset's profile passes. A missing (unresolved) metric SHALL fail its criterion.

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
