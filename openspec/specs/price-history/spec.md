# price-history Specification

## Purpose

Stores daily close prices for each tracked asset and derives per-asset market returns over a selected range, so the Dashboard can report best/worst universe performers over horizons (up to 1Y and Max) that on-demand market-data fetching cannot serve.

## Requirements

### Requirement: Stored daily price history per asset

The system SHALL persist a time series of daily close prices for each tracked asset. Each stored point SHALL record the asset, the trading date, and the close price, and SHALL be unique per asset and date so that re-ingesting a date updates rather than duplicates it. Each asset's series SHALL use that asset's own available trading dates, so assets that trade on different calendars (for example 24/7 crypto versus market-hours equities) are each stored on their own dates without inventing missing points.

#### Scenario: A date is stored once per asset

- **WHEN** a close price for an asset on a given trading date is ingested more than once
- **THEN** the system SHALL retain a single stored point for that asset and date, reflecting the most recently ingested close

#### Scenario: Assets keep their own trading calendars

- **WHEN** a crypto asset and an equity asset are both tracked
- **THEN** each asset's stored series SHALL contain only the dates on which that asset has a close, and the system SHALL NOT fabricate closes for dates an asset did not trade

### Requirement: Backfill price history when an asset is added

When a new asset is added to the universe, the system SHALL backfill its daily close history from the market-data provider up to a bounded lookback window, so that range-based returns are available for the asset without waiting for future daily ingestion to accumulate. If the provider cannot supply history for the asset, the add SHALL still succeed and the asset SHALL simply have no stored history until it can be ingested.

#### Scenario: History is backfilled on add

- **WHEN** an asset is successfully added to the universe
- **THEN** the system SHALL fetch and store that asset's available daily closes within the bounded lookback window

#### Scenario: Provider cannot supply history

- **WHEN** backfill is attempted but the provider returns no usable history for the asset
- **THEN** the asset SHALL remain added and the system SHALL store no price points for it rather than failing the add

### Requirement: Daily price-history ingestion

The system SHALL append the latest available daily closes for all tracked assets on a recurring daily schedule, triggered alongside the existing daily rebalancing cron. Ingestion SHALL be idempotent with respect to dates already stored and SHALL be resilient to per-asset provider failures, continuing to ingest the remaining assets when one asset cannot be fetched.

#### Scenario: Daily append of latest closes

- **WHEN** the daily ingestion runs
- **THEN** the system SHALL fetch and store each tracked asset's latest available closes that are not already stored, leaving previously stored points intact

#### Scenario: One asset fails to fetch

- **WHEN** the provider fails to return data for a single asset during daily ingestion
- **THEN** the system SHALL continue ingesting the remaining assets and SHALL NOT abort the whole run

### Requirement: Per-asset market return over a range

The system SHALL compute an asset's market return over a selected range from its stored daily closes as a close-to-close price return (dividends excluded). The range start SHALL be resolved against the asset's own available dates: for a fixed-length range the return SHALL be measured from the earliest stored close on or after the range start; for a year-to-date range from the first stored close of the current calendar year; and for the maximum range from the asset's earliest stored close. An asset without enough stored history to resolve a start point for the range SHALL be reported as having no return for that range rather than a misleading value.

#### Scenario: Return over a fixed range

- **WHEN** an asset's market return is requested for a fixed-length range (for example one month) and the asset has stored closes spanning that range
- **THEN** the system SHALL return the close-to-close percentage change from the first stored close at or after the range start to the latest stored close

#### Scenario: Year-to-date and maximum ranges

- **WHEN** an asset's return is requested for the year-to-date range or the maximum range
- **THEN** the system SHALL measure from the first stored close of the current calendar year, or from the asset's earliest stored close respectively, to the latest stored close

#### Scenario: Insufficient history for the range

- **WHEN** an asset lacks a stored close to resolve the start of the requested range
- **THEN** the system SHALL report no return for that asset and range rather than a value derived from an unrelated start point
