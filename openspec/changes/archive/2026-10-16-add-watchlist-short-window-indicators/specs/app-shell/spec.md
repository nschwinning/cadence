## MODIFIED Requirements

### Requirement: Watchlist view

The system SHALL provide a Watchlist view that lets the user trigger an
AI-driven watchlist recommendation run and browse the resulting watchlist
entries. Triggering a run SHALL reuse the asynchronous AI-run polling behavior
(showing the run as in-progress and updating to its terminal outcome without a
manual refresh). The view SHALL list the watchlist assets (those with
`watchlist` membership, kept separate from the universe/Assets view) and SHALL
surface each entry's available SEC EDGAR fundamentals (for example revenue,
margins, cash flow, earnings, and company details), indicating when an entry's
fundamentals are unavailable. The view SHALL also surface each entry's
**short-window technical-indicator profile** (the momentum/mean-reversion subset
suited to emerging names — for example RSI, MACD, EMA, Bollinger, historical
volatility, and volume signals), and SHALL show an explicit **insufficient
history** state for an entry whose price history is below the technical
minimum-history floor rather than rendering mostly-empty indicator values. The
view SHALL NOT present a long-window uptrend trend-gate verdict as a buy/sell
signal for watchlist entries. Errors from the API SHALL be surfaced with a
meaningful message.

#### Scenario: Trigger a watchlist recommendation

- **WHEN** a user starts an AI watchlist recommendation from the Watchlist view
- **THEN** the UI SHALL show the run as in-progress and SHALL automatically
  update to its final outcome when the run reaches a terminal state

#### Scenario: Browse watchlist entries with fundamentals

- **WHEN** a user opens the Watchlist view with watchlist assets present
- **THEN** the UI SHALL list those entries and display each one's available
  fundamentals, indicating any entry whose fundamentals could not be fetched

#### Scenario: Browse watchlist entries with technical indicators

- **WHEN** a user opens the Watchlist view with a watchlist asset whose history is at or above the technical minimum-history floor
- **THEN** the UI SHALL display that entry's short-window technical-indicator profile alongside its fundamentals

#### Scenario: Entry below the technical history floor

- **WHEN** a user opens the Watchlist view with a watchlist asset whose history is below the technical minimum-history floor
- **THEN** the UI SHALL show an explicit insufficient-history state for that entry's technical indicators rather than mostly-empty values

#### Scenario: Watchlist is separate from the universe

- **WHEN** a user views the Assets (universe) list and the Watchlist view
- **THEN** watchlist assets SHALL appear only in the Watchlist view and SHALL
  NOT appear in the universe asset list
