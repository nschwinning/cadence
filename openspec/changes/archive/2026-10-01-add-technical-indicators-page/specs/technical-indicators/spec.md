## ADDED Requirements

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
