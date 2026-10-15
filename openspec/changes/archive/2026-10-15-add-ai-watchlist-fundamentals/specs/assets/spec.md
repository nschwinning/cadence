## ADDED Requirements

### Requirement: Classify assets by universe membership

The system SHALL record a **membership** for every asset that is one of
`universe` (the tradable, curated universe) or `watchlist` (an emerging,
tracked-but-not-traded candidate). Membership SHALL default to `universe`:
manual adds and universe-recommendation additions SHALL create `universe`
assets, and every asset existing before this change SHALL be treated as a
`universe` member. Membership SHALL be **orthogonal to eligibility** — a
watchlist asset is still evaluated and carries an eligibility flag; its
membership does not change its eligibility and its eligibility does not change
its membership.

Every internal read of "the asset universe" SHALL be restricted to `universe`
members so that watchlist assets never participate as trading candidates, in the
recommender's exclusion/aggregate inputs, or in the universe evaluation. Reading
or deleting a single asset by id/ticker SHALL work regardless of its membership.

#### Scenario: Existing assets are universe members

- **WHEN** the membership classification is introduced over an existing universe
- **THEN** every pre-existing asset SHALL be a `universe` member and continue to
  appear and behave exactly as before

#### Scenario: Manual and universe-recommendation adds are universe members

- **WHEN** an asset is added manually by ticker, or added by a universe-targeted
  recommendation run
- **THEN** the system SHALL persist it as a `universe` member

#### Scenario: Watchlist assets are excluded from universe reads

- **WHEN** the AI build or rebalance reads trading candidates, the recommender
  computes its exclusion/aggregate inputs, or the universe evaluation summarizes
  the universe
- **THEN** only `universe` members SHALL be included and `watchlist` members
  SHALL be excluded

#### Scenario: A watchlist asset can be an ineligible member

- **WHEN** a watchlist asset fails one or more maturity criteria (for example
  insufficient history or market capitalization)
- **THEN** the system SHALL still store it as a `watchlist` member with its
  eligibility flag set to false and its per-criterion results recorded

### Requirement: Fetch and persist company fundamentals from SEC EDGAR

When a watchlist (equity) asset is created, the system SHALL fetch its company
fundamentals from SEC EDGAR — resolving the ticker to a CIK via EDGAR's
published ticker→CIK mapping, then reading the company's reported facts — and
SHALL persist them associated with the asset. The stored fundamentals SHALL
capture revenue, margin inputs (for example gross/operating/net figures), cash
flow, earnings, and company details available from the filing data. Fundamentals
persistence SHALL be general-purpose per asset (not watchlist-only) so the same
store can later hold fundamentals for universe assets.

Fetching SHALL degrade gracefully: if EDGAR has no CIK for the ticker, returns
no usable facts, or is unreachable, asset creation SHALL still succeed with the
fundamentals recorded as unavailable (or partially populated) rather than
failing the whole operation. All EDGAR network access SHALL be confined to a
single provider seam so it can be faked in tests with no network.

#### Scenario: Fundamentals fetched on watchlist asset creation

- **WHEN** a watchlist equity asset is created and EDGAR has reported facts for
  its ticker
- **THEN** the system SHALL persist the asset's fundamentals (revenue, margins,
  cash flow, earnings, company details) linked to the asset

#### Scenario: EDGAR has no data for the ticker

- **WHEN** a watchlist asset is created but EDGAR has no CIK or no usable facts
  for the ticker
- **THEN** the system SHALL still create the asset and SHALL record its
  fundamentals as unavailable rather than failing creation

#### Scenario: EDGAR is unreachable

- **WHEN** the EDGAR provider errors or times out during watchlist asset creation
- **THEN** the system SHALL still create the asset and SHALL record its
  fundamentals as unavailable, leaving the asset otherwise intact

## MODIFIED Requirements

### Requirement: List assets with pagination, search, sorting, and filtering

The system SHALL return a paginated list of assets with a total count. It SHALL
support a bounded page size chosen from an allowed set, an offset, a
case-insensitive substring search over ticker and name, sorting by an allowed
field and direction with deterministic tie-breaking, and repeatable filters by
category and by sector validated against the known value sets. The list SHALL
also support filtering by **membership**; when no membership filter is supplied
the list SHALL return only `universe` members so the universe management view is
unaffected by watchlist assets.

#### Scenario: Default listing

- **WHEN** a client requests the asset list without parameters
- **THEN** the system SHALL return the first page of `universe` members and the
  total count of `universe` members

#### Scenario: Filter by membership

- **WHEN** a client requests the asset list filtered to `watchlist` membership
- **THEN** the system SHALL return only `watchlist` members with the total
  reflecting that filtered set

#### Scenario: Search and filter

- **WHEN** a client provides a search term and one or more category/sector filters
- **THEN** the system SHALL return only assets matching the search term AND all
  supplied filters, with the total reflecting the filtered set

#### Scenario: Invalid pagination or sort parameter

- **WHEN** a client supplies a page size, sort field, direction, category,
  sector, or membership outside the allowed set
- **THEN** the system SHALL respond with a validation error (422)
