# technical-indicators Specification

## Purpose

Compute a fixed set of price-trend and momentum indicators — restricted to closing
price and volume — for every asset in the universe on a nightly schedule, derive a
deterministic uptrend verdict and a set of reversal flags from them, and store the
latest snapshot per asset so the trading flows can gate new entries and give the AI
trend context when judging existing holdings.

## Requirements

### Requirement: Compute close+volume technical indicators per asset

The system SHALL compute, for a given asset, a fixed set of technical indicators
derived solely from its daily closing-price and volume history: the 50- and
200-period simple moving averages and the price/SMA200 and SMA50/SMA200 ratios, the
20-day slope of SMA200, the 20-period exponential moving average, the MACD line,
signal, and histogram (12/26/9), the 14-period Wilder RSI, the 120-day rate of
change, on-balance volume and its 20-day change, the volume ratio versus the
50-day average volume, the distance from the trailing 52-week high, the drawdown
from the trailing 252-day maximum, the 20-day historical volatility, and the
Bollinger %b and bandwidth (20-period, 2 standard deviations). The computation
SHALL use only close/adjusted-close and volume series and SHALL NOT require
open/high/low inputs. When an asset has insufficient history to compute an
indicator, that indicator's value SHALL be absent (null) rather than causing the
computation to fail.

#### Scenario: Indicators computed from close and volume

- **WHEN** the system computes indicators for an asset that has sufficient daily close and volume history
- **THEN** the system SHALL produce the full fixed indicator set for that asset from its close and volume series alone

#### Scenario: Insufficient history yields absent values

- **WHEN** an asset has too little history to compute a given indicator (for example fewer than 200 closes for SMA200)
- **THEN** the system SHALL record that indicator as absent for the asset rather than failing the run

### Requirement: Derive a deterministic trend gate and reversal flags

The system SHALL derive, from an asset's computed indicators, a deterministic
"uptrend" gate verdict and a set of deterministic reversal flags. The uptrend gate
SHALL pass only when both a regime condition and a momentum condition hold: the
regime condition SHALL require the latest close above SMA200 AND SMA50 above SMA200
AND a non-negative SMA200 slope; the momentum condition SHALL require a positive
MACD histogram AND RSI above 50 AND a positive 120-day rate of change. A rising OBV
SHALL be recorded as a soft bonus signal but SHALL NOT be required for the gate to
pass. The reversal flags SHALL be booleans derived deterministically from the same
indicators — at minimum: MACD-histogram rollover (histogram turning down), RSI
peaking/rollover, decelerating/negative return acceleration, a simple OBV/price
divergence proxy over a fixed lookback (price making a new N-day high while OBV or
RSI does not), and SMA200-slope flattening. The gate thresholds and lookbacks SHALL
be tunable constants. When a required indicator is absent, the gate SHALL evaluate
to fail (an asset is not confirmed as an uptrend when its trend cannot be
established).

#### Scenario: Gate passes on a confirmed uptrend

- **WHEN** an asset's indicators satisfy both the regime condition and the momentum condition
- **THEN** the system SHALL report the uptrend gate as passing for that asset

#### Scenario: Gate fails when regime or momentum is not met

- **WHEN** an asset fails the regime condition or the momentum condition (or a required indicator is absent)
- **THEN** the system SHALL report the uptrend gate as failing for that asset

#### Scenario: Reversal flags derived for an asset

- **WHEN** the system evaluates an asset's indicators
- **THEN** the system SHALL produce the deterministic reversal flags (MACD-histogram rollover, RSI rollover, return deceleration, OBV/price divergence proxy, SMA200-slope flattening) as boolean signals

### Requirement: Store the latest indicator snapshot per asset

The system SHALL persist, per asset, the latest computed indicator snapshot — one
row per asset carrying the asset reference, the trading date the snapshot was
computed for, every computed indicator value, the derived uptrend-gate verdict, and
the derived reversal flags. Re-running the computation for an asset SHALL replace
that asset's stored snapshot (delete-then-insert or upsert) rather than accumulate
historical rows, so a read always sees the most recent snapshot. A read of an
asset's indicators SHALL return its stored snapshot, or absent when no snapshot has
been computed yet.

#### Scenario: Snapshot replaced on recomputation

- **WHEN** the indicator computation runs for an asset that already has a stored snapshot
- **THEN** the system SHALL replace that asset's snapshot with the newly computed values rather than create a second row

#### Scenario: Read an asset's latest snapshot

- **WHEN** a trading flow reads an asset's indicators
- **THEN** the system SHALL return the asset's latest stored snapshot, or absent when none has been computed

### Requirement: Nightly indicator computation job with run audit

The system SHALL provide a background job that computes and stores indicator
snapshots for every asset in the universe, executed by a single-worker runner so
that only one computation run proceeds at a time. Each run SHALL be recorded as an
audit entry capturing at least the run's status, its start and finish, and counts
of assets processed and failed. A failure to compute one asset's indicators SHALL
be recorded and SHALL NOT abort the run for the remaining assets. The job SHALL be
processed in the background and SHALL commit progress per asset so a mid-run
failure preserves the snapshots already computed.

#### Scenario: Job computes snapshots for the universe

- **WHEN** the indicator computation job runs
- **THEN** the system SHALL compute and store a latest snapshot for each asset in the universe and record a run-audit entry summarizing the outcome

#### Scenario: One asset's failure does not abort the run

- **WHEN** computing indicators for one asset fails during a run
- **THEN** the system SHALL record the failure, continue computing the remaining assets, and reflect the failed count in the run audit

#### Scenario: Single-worker execution

- **WHEN** an indicator computation run is requested while one is already running
- **THEN** the system SHALL not start a second concurrent run

### Requirement: Cron-guarded indicator computation trigger

The system SHALL expose an endpoint that triggers the nightly indicator computation
job. The endpoint SHALL be protected by the shared cron-token secret supplied in a
request header; a missing or incorrect token SHALL be rejected, and when the
configured token is empty every request SHALL be rejected. The endpoint SHALL start
the computation in the background and return immediately.

#### Scenario: Valid token triggers computation

- **WHEN** the endpoint is called with the correct cron token
- **THEN** the system SHALL start the indicator computation job in the background and respond immediately

#### Scenario: Invalid or missing token

- **WHEN** the endpoint is called without a token or with an incorrect token, or the configured token is empty
- **THEN** the system SHALL reject the request and SHALL NOT start a computation run

### Requirement: Expose the technical-indicator configuration for reading

The system SHALL expose the configured technical-indicator setup over an unauthenticated read-only endpoint so clients can display what the trend strategy computes and how it decides. The response SHALL describe, from the system's current configuration rather than hard-coded duplicates: the fixed indicator set (each indicator's identity and the period/lookback parameters that define it), the deterministic uptrend trend-gate rules together with their thresholds (the regime conditions, the momentum conditions, and that a rising-volume signal is a soft bonus rather than a required condition), the rule that a missing required indicator fails the gate, and the reversal-flag definitions together with their thresholds. The endpoint SHALL NOT require the cron token or any other authentication, and SHALL NOT trigger or alter indicator computation. When the response reflects a change to the underlying configured thresholds or periods, the returned values SHALL change accordingly.

#### Scenario: Read the indicator configuration

- **WHEN** a client requests the technical-indicator configuration
- **THEN** the system SHALL return the configured indicator set with its period/lookback parameters, the trend-gate rules and thresholds, and the reversal-flag definitions and thresholds, without requiring authentication and without starting a computation

#### Scenario: Configuration reflects the backend thresholds

- **WHEN** the configured thresholds or periods differ from a previous value
- **THEN** the returned configuration SHALL report the current values rather than stale or duplicated constants

#### Scenario: Read endpoint is not cron-guarded

- **WHEN** a client requests the configuration without supplying the cron token
- **THEN** the system SHALL return the configuration successfully rather than rejecting the request for a missing token
