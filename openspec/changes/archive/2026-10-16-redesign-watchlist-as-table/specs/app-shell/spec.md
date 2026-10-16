## REMOVED Requirements

### Requirement: Watchlist view

**Reason**: The watchlist is being redesigned from a card list that inlines each
entry's fundamentals and technical-indicator panels into a searchable/sortable/
filterable table whose rows link to the asset detail view. The inline-fundamentals
and inline-technical scenarios no longer describe the watchlist view, so the whole
requirement is replaced by the new "Watchlist view" and "Asset detail fundamentals
and technical indicators" requirements below.

**Migration**: Fundamentals and the short-window technical-indicator profile (and the
insufficient-history state) are now shown on the shared asset detail view
(`/assets/:ticker`), reached by clicking a watchlist table row. The AI watchlist
recommendation run and the watchlist-separate-from-universe behavior are preserved by
the new "Watchlist table view" requirement.

## ADDED Requirements

### Requirement: Watchlist table view

The system SHALL provide a Watchlist view that lets the user trigger an
AI-driven watchlist recommendation run and browse the resulting watchlist
entries. Triggering a run SHALL reuse the asynchronous AI-run polling behavior
(showing the run as in-progress and updating to its terminal outcome without a
manual refresh). The view SHALL present the watchlist assets (those with
`watchlist` membership, kept separate from the universe/Assets view) as a
**searchable, sortable, and filterable table** mirroring the Assets list: a
text search over ticker/name, sortable ticker and name columns, and
category/sector filters. Each row SHALL link to that asset's detail view, where
the asset's fundamentals and technical indicators are shown. The watchlist view
SHALL NOT render each entry's fundamentals or technical-indicator values inline
in the list (those are surfaced on the asset detail view). Errors from the API
SHALL be surfaced with a meaningful message.

#### Scenario: Trigger a watchlist recommendation

- **WHEN** a user starts an AI watchlist recommendation from the Watchlist view
- **THEN** the UI SHALL show the run as in-progress and SHALL automatically
  update to its final outcome when the run reaches a terminal state

#### Scenario: Browse the watchlist as a table

- **WHEN** a user opens the Watchlist view with watchlist assets present
- **THEN** the UI SHALL list those entries in a table that can be searched by
  ticker/name, sorted by ticker and name, and filtered by category and sector

#### Scenario: Jump from a watchlist row to the asset detail

- **WHEN** a user selects a watchlist entry's row
- **THEN** the UI SHALL open that asset's detail view, where its fundamentals
  and technical indicators are shown

#### Scenario: Watchlist is separate from the universe

- **WHEN** a user views the Assets (universe) list and the Watchlist view
- **THEN** watchlist assets SHALL appear only in the Watchlist view and SHALL
  NOT appear in the universe asset list

### Requirement: Asset detail fundamentals and technical indicators

The asset detail view SHALL display, for the opened asset, its available SEC
EDGAR fundamentals (for example revenue, margins, cash flow, earnings, and
company details), indicating when the asset's fundamentals are unavailable. The
asset detail view SHALL also display the asset's **short-window
technical-indicator profile** (the momentum/mean-reversion subset — for example
RSI, MACD, EMA, Bollinger, historical volatility, and volume signals), and SHALL
show an explicit **insufficient-history** state when the asset's price history is
below the technical minimum-history floor rather than rendering mostly-empty
indicator values. These sections SHALL render for any asset (universe or
watchlist) through the same detail view. The asset detail view SHALL NOT present
a long-window uptrend trend-gate verdict as a buy/sell signal. Errors loading the
fundamentals or technical data SHALL be surfaced with a meaningful message and
SHALL NOT prevent the rest of the detail view from rendering.

#### Scenario: Detail shows fundamentals when available

- **WHEN** a user opens the detail view for an asset that has fundamentals
- **THEN** the UI SHALL display that asset's available fundamentals

#### Scenario: Detail indicates unavailable fundamentals

- **WHEN** a user opens the detail view for an asset whose fundamentals could not be fetched or do not exist
- **THEN** the UI SHALL indicate that the asset's fundamentals are unavailable rather than showing empty values

#### Scenario: Detail shows the short-window technical profile

- **WHEN** a user opens the detail view for an asset whose history is at or above the technical minimum-history floor and whose indicator snapshot exists
- **THEN** the UI SHALL display that asset's short-window technical-indicator profile

#### Scenario: Detail shows an insufficient-history state

- **WHEN** a user opens the detail view for an asset whose history is below the technical minimum-history floor
- **THEN** the UI SHALL show an explicit insufficient-history state for the technical indicators rather than mostly-empty values
