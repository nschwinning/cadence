## MODIFIED Requirements

### Requirement: Nightly indicator computation job with run audit

The system SHALL provide a background job that computes and stores indicator
snapshots for every asset in the universe **and for every watchlist asset**,
executed by a single-worker runner so that only one computation run proceeds at a
time. Each run SHALL be recorded as an audit entry capturing at least the run's
status, its start and finish, and counts of assets processed and failed. A
failure to compute one asset's indicators SHALL be recorded and SHALL NOT abort
the run for the remaining assets. The job SHALL be processed in the background and
SHALL commit progress per asset so a mid-run failure preserves the snapshots
already computed.

#### Scenario: Job computes snapshots for the universe

- **WHEN** the indicator computation job runs
- **THEN** the system SHALL compute and store a latest snapshot for each asset in the universe and record a run-audit entry summarizing the outcome

#### Scenario: Job computes snapshots for watchlist assets

- **WHEN** the indicator computation job runs while watchlist assets exist
- **THEN** the system SHALL also compute and store a latest snapshot (or an insufficient-history marker) for each watchlist asset, included in the same run audit's processed/failed counts

#### Scenario: One asset's failure does not abort the run

- **WHEN** computing indicators for one asset fails during a run
- **THEN** the system SHALL record the failure, continue computing the remaining assets, and reflect the failed count in the run audit

#### Scenario: Single-worker execution

- **WHEN** an indicator computation run is requested while one is already running
- **THEN** the system SHALL not start a second concurrent run

## ADDED Requirements

### Requirement: Watchlist short-window indicator profile with a minimum-history floor

For watchlist assets the system SHALL expose a **short-window** subset of the
computed indicators as the meaningful technical profile, because watchlist assets
are emerging companies whose history is typically too short for the long-window
indicators and the uptrend trend gate to be meaningful. The short-window profile
SHALL consist of: the 14-period Wilder RSI, the MACD line/signal/histogram
(12/26/9), the 20-period exponential moving average, the Bollinger %b and
bandwidth (20-period, 2 standard deviations), the 20-day historical volatility,
the volume ratio versus the 50-day average volume, the on-balance-volume 20-day
change, and the reversal flags whose inputs are entirely short-window. The
long-window indicators (the 50- and 200-period simple moving averages and their
ratios, the SMA200 slope, the 120-day rate of change, the distance from the
52-week high, and the 252-day drawdown) and the derived uptrend trend-gate verdict
SHALL NOT be presented as a trading signal for watchlist assets.

The system SHALL apply a **minimum-history floor**, a tunable constant number of
daily bars, below which a watchlist asset's short-window profile is not
meaningful. A watchlist asset with fewer daily bars than the floor SHALL be
recorded with an **insufficient-history** marker rather than a snapshot of
mostly-absent short-window values; at or above the floor the short-window values
SHALL be produced and stored. A read of a watchlist asset's indicators SHALL
expose the short-window subset together with the insufficient-history marker.

This requirement governs only how indicators are surfaced for watchlist assets;
it SHALL NOT make watchlist assets eligible for trading and SHALL NOT alter the
universe trend gate or any trading flow.

#### Scenario: Watchlist asset at or above the floor gets the short-window profile

- **WHEN** the computation job processes a watchlist asset whose daily-bar count is at or above the minimum-history floor
- **THEN** the system SHALL store its short-window indicator values and expose them on read, without an insufficient-history marker

#### Scenario: Watchlist asset below the floor is marked insufficient history

- **WHEN** the computation job processes a watchlist asset whose daily-bar count is below the minimum-history floor
- **THEN** the system SHALL record an insufficient-history marker for that asset rather than a snapshot of mostly-absent short-window values

#### Scenario: Trend-gate verdict is not a watchlist trading signal

- **WHEN** a watchlist asset's indicators are read
- **THEN** the system SHALL expose the short-window subset and SHALL NOT present the long-window indicators or the uptrend trend-gate verdict as a trading signal for that asset
