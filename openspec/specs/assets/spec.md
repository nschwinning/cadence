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

### Requirement: Generate and persist an AI evaluation of the asset universe

The system SHALL generate an AI-authored evaluation of the entire asset universe
and persist exactly one current evaluation. The evaluation SHALL be markdown
narrative plus bulleted key findings (strengths, concerns, and suggestions)
assessing diversification, sector/category concentration, quality, notable gaps,
and foreign or unpriceable listings. The persisted record SHALL include the
generated content, the time it was generated, and a fingerprint of the universe
captured at generation time. Generating a new evaluation SHALL replace the
previous record; no history is retained.

The evaluation SHALL respect Cadence's supported trading scope: the universe may
only contain US Alpaca-tradable individual equities and crypto, managed long-only
with full-universe weight allocation (no shorting, leverage, options, or
derivatives), and SHALL NOT hold ETFs, mutual funds, bond funds, fixed-income
instruments, cash-equivalent or money-market funds, or foreign (non-US-listed)
securities. The evaluation's suggestions SHALL stay within that scope — for
example adding specific individual stocks or crypto, reducing concentration,
addressing quality or sector gaps, or resolving foreign/unpriceable listings to
their US listing or ADR — and SHALL NOT recommend any instrument class Cadence
does not support.

#### Scenario: Generate an evaluation

- **WHEN** an evaluation is generated for a non-empty universe
- **THEN** the system summarizes the universe (counts by category and sector,
  eligibility counts, concentration, and foreign/unpriceable listings), requests
  an AI narrative with bulleted findings, and stores the content together with the
  generation time and the universe fingerprint

#### Scenario: Only one current evaluation is kept

- **WHEN** an evaluation already exists and a new one is generated
- **THEN** the stored record (content, fingerprint, and generation time) is
  replaced by the new evaluation and no prior evaluation remains

#### Scenario: AI provider unavailable during generation

- **WHEN** generation is requested but the AI provider cannot be reached or returns
  no usable result
- **THEN** no evaluation is stored or replaced and the caller receives an error
  indicating the evaluation could not be generated

#### Scenario: Suggestions stay within the supported scope

- **WHEN** an evaluation is generated
- **THEN** the prompt given to the AI states that Cadence's universe may only hold
  US-tradable individual stocks and crypto, is managed long-only, and cannot hold
  ETFs, funds, fixed-income, cash-equivalents, or foreign listings, so that the
  evaluation's suggestions propose only in-scope actions and do not recommend
  unsupported instrument classes

### Requirement: Lazy-fill the evaluation on first read

The system SHALL generate and persist the evaluation the first time it is read when
none exists yet, and SHALL return the stored evaluation without regenerating on
subsequent reads.

#### Scenario: First read with no evaluation

- **WHEN** the evaluation is read and none has ever been generated
- **THEN** the system generates one, persists it, and returns it

#### Scenario: Subsequent read returns the stored evaluation

- **WHEN** the evaluation is read and a current evaluation already exists
- **THEN** the system returns the stored evaluation without generating a new one

### Requirement: Flag the evaluation as outdated when the universe changes

On read, the system SHALL recompute a fingerprint over the current universe and
compare it to the fingerprint stored with the evaluation. The evaluation SHALL be
reported as outdated when the two fingerprints differ. The fingerprint SHALL be
derived from each asset's mutable attributes so that it changes when assets are
added or removed and when an existing asset's attributes change (including the
nightly metric refresh).

#### Scenario: Universe unchanged since generation

- **WHEN** the evaluation is read and no asset has changed since it was generated
- **THEN** the evaluation is reported as not outdated

#### Scenario: Asset added or removed since generation

- **WHEN** an asset has been added to or removed from the universe since the
  evaluation was generated
- **THEN** reading the evaluation reports it as outdated

#### Scenario: Existing asset changed since generation

- **WHEN** an existing asset's attributes have changed since the evaluation was
  generated (for example a metric refresh or eligibility change)
- **THEN** reading the evaluation reports it as outdated

### Requirement: Read and refresh the asset universe evaluation via the API

The system SHALL expose an endpoint to read the current evaluation — returning its
content, its generation time, and whether it is outdated — and an endpoint to
refresh (regenerate) it on demand. The read endpoint SHALL lazy-fill when no
evaluation exists; the refresh endpoint SHALL always regenerate and replace the
stored evaluation.

#### Scenario: Read the current evaluation

- **WHEN** a client requests the current evaluation
- **THEN** the response includes the narrative, the key findings, the generation
  time, and an outdated flag computed against the current universe

#### Scenario: Refresh the evaluation on request

- **WHEN** a client requests a refresh
- **THEN** the system regenerates the evaluation against the current universe,
  replaces the stored record, and returns the new evaluation reported as not
  outdated

#### Scenario: Read an empty universe

- **WHEN** the evaluation is read while the universe contains no assets
- **THEN** the system does not call the AI provider and the response indicates no
  evaluation is available

### Requirement: Backfill the brokerage symbol for unverified assets

The system SHALL provide a one-off, re-runnable operation that resolves the brokerage's canonical symbol for existing assets that lack one (assets whose stored brokerage symbol is absent because they were added before add-time brokerage verification). For each such asset, the system SHALL look the asset up on the brokerage using the asset's category to determine its asset class, and SHALL store the brokerage's canonical symbol when the brokerage lists the asset as tradable. An asset the brokerage does not list, or lists as not tradable, SHALL be left without a brokerage symbol so it remains identifiable as not tradable. The operation SHALL be fail-open — a failure resolving one asset SHALL be recorded and skipped without aborting the rest — and SHALL be idempotent, so it may be re-run safely and only ever fills in assets still missing a symbol. The operation SHALL report how many assets it updated. The operation SHALL NOT alter assets that already have a brokerage symbol.

#### Scenario: Resolve a tradable legacy asset

- **WHEN** the backfill runs and an asset without a brokerage symbol is listed by the brokerage as tradable
- **THEN** the system SHALL store the brokerage's canonical symbol on that asset (even when it differs from the asset's ticker) and count it as updated

#### Scenario: Leave a genuinely untradable asset flagged

- **WHEN** the backfill runs and an asset without a brokerage symbol is not listed by the brokerage, or is listed as not tradable
- **THEN** the system SHALL leave that asset without a brokerage symbol so it remains identifiable as not tradable, and SHALL NOT count it as updated

#### Scenario: One asset's failure does not abort the pass

- **WHEN** the backfill runs and resolving one asset raises an error
- **THEN** the system SHALL record the failure, leave that asset without a brokerage symbol, and continue resolving the remaining assets

#### Scenario: Idempotent and non-destructive on re-run

- **WHEN** the backfill is run again after a previous run
- **THEN** the system SHALL only attempt assets still missing a brokerage symbol and SHALL NOT modify assets that already have one
