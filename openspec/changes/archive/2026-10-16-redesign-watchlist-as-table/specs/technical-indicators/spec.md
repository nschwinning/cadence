## ADDED Requirements

### Requirement: Per-asset short-window indicator read

The system SHALL expose a read that returns the short-window technical-indicator
profile for a single asset identified by ticker, for an asset of any universe
membership (universe or watchlist). The response SHALL carry the same short-window
subset defined for watchlist assets — the 14-period Wilder RSI, the MACD
line/signal/histogram, the 20-period EMA, the Bollinger %b and bandwidth, the
20-day historical volatility, the volume ratio versus the 50-day average volume,
the on-balance-volume 20-day change, and the short-window reversal flags — together
with the minimum-history floor and an insufficient-history marker, derived from the
asset's latest stored indicator snapshot. The read SHALL apply the same
minimum-history floor semantics: an asset below the floor SHALL be reported with an
insufficient-history marker rather than mostly-absent values. The read SHALL report
an asset that has no stored snapshot as absent/insufficient rather than failing, and
SHALL respond not-found when the ticker is not in the universe. The read SHALL NOT
present the long-window indicators or the uptrend trend-gate verdict as a trading
signal, SHALL NOT require the cron token or any other authentication, and SHALL NOT
trigger or alter indicator computation.

#### Scenario: Read a universe asset's short-window profile

- **WHEN** a client requests the per-asset technical read for a universe asset whose daily-bar count is at or above the minimum-history floor and whose snapshot has been computed
- **THEN** the system SHALL return that asset's short-window indicator values and the minimum-history floor, without an insufficient-history marker and without the uptrend trend-gate verdict

#### Scenario: Read a watchlist asset's short-window profile

- **WHEN** a client requests the per-asset technical read for a watchlist asset whose daily-bar count is at or above the minimum-history floor
- **THEN** the system SHALL return that asset's short-window indicator values and the minimum-history floor

#### Scenario: Asset below the minimum-history floor

- **WHEN** a client requests the per-asset technical read for an asset whose daily-bar count is below the minimum-history floor
- **THEN** the system SHALL return an insufficient-history marker for that asset rather than mostly-absent short-window values

#### Scenario: Asset without a computed snapshot

- **WHEN** a client requests the per-asset technical read for an existing asset that has no stored indicator snapshot
- **THEN** the system SHALL report the profile as absent/insufficient rather than failing the request

#### Scenario: Read for an unknown ticker

- **WHEN** a client requests the per-asset technical read for a ticker that is not in the universe
- **THEN** the system SHALL respond not-found
