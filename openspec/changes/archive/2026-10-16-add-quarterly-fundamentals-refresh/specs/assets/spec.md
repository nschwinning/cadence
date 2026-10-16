## ADDED Requirements

### Requirement: Periodically refresh stock fundamentals on a quarterly schedule

The system SHALL provide a periodic refresh job that re-fetches SEC EDGAR company
fundamentals for **every stock asset** in the universe and persists the refreshed
data, keeping fundamentals current with quarterly filings rather than frozen at
each asset's first fetch. The refresh SHALL cover all assets classified as stock
regardless of universe membership (universe or watchlist) and regardless of
eligibility or brokerage tradability; crypto assets SHALL be excluded. On each
run the refresh SHALL re-fetch **all** in-scope stock assets — it SHALL NOT skip
assets based on how recently their fundamentals were last fetched — and SHALL
upsert each asset's single fundamentals record (creating it when absent,
otherwise overwriting the stored source, status, CIK, and figures) and advance
its fetched-at timestamp.

The refresh SHALL be **best-effort per asset**: a failure to fetch or persist one
asset's fundamentals SHALL NOT abort the batch or prevent the remaining assets
from being refreshed, and — consistent with the existing fetch behavior — an
asset whose ticker EDGAR cannot resolve, that returns no usable facts, or that is
unreachable SHALL have its fundamentals recorded as unavailable (or partially
populated) rather than causing an error. All EDGAR network access SHALL remain
confined to the existing provider seam so the refresh can be exercised in tests
with no network.

The refresh SHALL return a summary of the run — at least the number of stock
assets considered and the number refreshed — so the outcome is observable.

The refresh SHALL be invokable through a dedicated endpoint intended for
scheduled invocation, guarded by the shared cron-token secret: a request without
a valid cron token SHALL be rejected and SHALL NOT run the refresh, and the
scheduled cadence SHALL default to quarterly and SHALL be configurable.

#### Scenario: Refresh re-fetches fundamentals for all stock assets

- **WHEN** the fundamentals refresh runs and the universe contains stock assets
- **THEN** the system SHALL fetch SEC EDGAR fundamentals for every stock asset and
  upsert each asset's fundamentals record, advancing its fetched-at timestamp,
  regardless of when that asset's fundamentals were previously fetched

#### Scenario: Crypto assets are excluded from the refresh

- **WHEN** the fundamentals refresh runs and the universe contains both stock and
  crypto assets
- **THEN** the system SHALL refresh fundamentals only for the stock assets and
  SHALL NOT attempt to fetch fundamentals for the crypto assets

#### Scenario: One asset's failure does not abort the batch

- **WHEN** the fundamentals refresh runs and EDGAR has no data for, or errors on,
  one or more stock assets
- **THEN** the system SHALL record those assets' fundamentals as unavailable (or
  partially populated) and SHALL still refresh the remaining stock assets

#### Scenario: Refresh reports a summary

- **WHEN** the fundamentals refresh completes
- **THEN** the system SHALL report a summary including at least the number of
  stock assets considered and the number refreshed

#### Scenario: Refresh endpoint requires the cron token

- **WHEN** the fundamentals refresh endpoint is called without a valid cron token
- **THEN** the system SHALL reject the request and SHALL NOT run the refresh

#### Scenario: Refresh endpoint runs with a valid cron token

- **WHEN** the fundamentals refresh endpoint is called with a valid cron token
- **THEN** the system SHALL run the refresh across the stock assets and return the
  run summary

## MODIFIED Requirements

### Requirement: Fetch and persist company fundamentals from SEC EDGAR

When a stock (equity) asset is created — through any creation path (a manual add
or an AI recommendation run, for any universe membership) — the system SHALL fetch
its company fundamentals from SEC EDGAR — resolving the ticker to a CIK via
EDGAR's published ticker→CIK mapping, then reading the company's reported facts —
and SHALL persist them associated with the asset. The stored fundamentals SHALL
capture revenue, margin inputs (for example gross/operating/net figures), cash
flow, earnings, and company details available from the filing data. Fundamentals
persistence SHALL be general-purpose per asset, holding at most one fundamentals
record per asset. Creating a crypto asset SHALL NOT trigger a fundamentals fetch,
and the absence of a fundamentals record for a crypto asset SHALL be a valid
state.

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

#### Scenario: Fundamentals fetched on a non-watchlist stock asset creation

- **WHEN** a stock (equity) asset is created outside the watchlist — a manual add
  or a universe-targeted recommendation run — and EDGAR has reported facts for its
  ticker
- **THEN** the system SHALL persist the asset's fundamentals (revenue, margins,
  cash flow, earnings, company details) linked to the asset

#### Scenario: Crypto asset creation does not fetch fundamentals

- **WHEN** a crypto asset is created
- **THEN** the system SHALL NOT fetch fundamentals for it, and the asset SHALL be
  created with no fundamentals record

#### Scenario: EDGAR has no data for the ticker

- **WHEN** a stock asset is created but EDGAR has no CIK or no usable facts for
  the ticker
- **THEN** the system SHALL still create the asset and SHALL record its
  fundamentals as unavailable rather than failing creation

#### Scenario: EDGAR is unreachable

- **WHEN** the EDGAR provider errors or times out during stock asset creation
- **THEN** the system SHALL still create the asset and SHALL record its
  fundamentals as unavailable, leaving the asset otherwise intact
