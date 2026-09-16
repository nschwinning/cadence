## RENAMED Requirements

- FROM: `### Requirement: EUR-based eligibility evaluation`
- TO: `### Requirement: USD-based eligibility evaluation`

## MODIFIED Requirements

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
