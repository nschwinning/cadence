## Purpose

Provides an on-demand, read-only view of whether the application's external backends (broker, web search, market data, and AI model) are configured and currently reachable, so an operator can diagnose connectivity at a glance without reading logs or exposing any secret.

## ADDED Requirements

### Requirement: Report the status of connected backends

The system SHALL expose a read-only operation that reports the current status of each external backend the application depends on: the **broker** (Alpaca), the **web-search provider**, the **market-data provider** (yfinance), and the **AI model provider** (OpenAI). For each backend the report SHALL include: a stable backend name; whether the backend is **configured** (its required credentials/settings are present); a non-secret **identifier** describing how it is set up (for the broker its mode — paper, live, or stub; for web search the active provider name; for the AI model the configured model id); whether it is **reachable** (the result of a live probe, or absent when no probe was performed); the probe **latency** in milliseconds when a probe was performed; and a short human-readable **detail** message (for example an error summary) when relevant. The operation SHALL require no request body and SHALL NOT be guarded by the cron-token secret.

#### Scenario: Report lists every backend

- **WHEN** a client requests the system status
- **THEN** the system SHALL return one status entry for each of the broker, web-search provider, market-data provider, and AI model provider, each with its name, configured flag, non-secret identifier, reachable result, latency, and optional detail

### Requirement: Live-probe each backend with isolation and a bounded timeout

The system SHALL determine reachability by performing a lightweight live probe against each backend at request time, using the cheapest call that validates connectivity (and, where applicable, credentials and the configured model). Each probe SHALL be isolated: a failure, error, or timeout of one backend's probe SHALL NOT prevent the other backends from being probed or reported, and SHALL NOT fail the overall operation — the operation SHALL return a successful response carrying the per-backend outcomes regardless of any individual backend being unreachable. Each probe SHALL be bounded by a short timeout so that a slow or hung backend cannot delay the overall response beyond that bound; a probe that exceeds its timeout SHALL be reported as unreachable with a detail indicating the timeout.

#### Scenario: One unreachable backend does not fail the report

- **WHEN** a client requests the system status and one backend's probe fails or times out
- **THEN** the system SHALL still return a successful response in which the failing backend is marked unreachable (with a detail) and every other backend is reported with its own probe result

#### Scenario: A reachable backend reports latency

- **WHEN** a backend's live probe succeeds
- **THEN** the system SHALL mark that backend reachable and report the measured probe latency

#### Scenario: Probe is bounded by a timeout

- **WHEN** a backend does not respond within the probe's timeout
- **THEN** the system SHALL stop waiting, mark that backend unreachable with a timeout detail, and continue reporting the other backends

### Requirement: Do not probe or expose unavailable backends unsafely

The system SHALL NOT perform a network probe for a backend that cannot meaningfully be probed, and SHALL report it accordingly rather than erroring. When a backend is not configured (its required credentials/settings are absent), the system SHALL report it as not configured with no reachability result rather than attempting a probe. When the broker is running in offline/stub mode, the system SHALL report the stub mode and SHALL NOT make any network call for it.

#### Scenario: Unconfigured backend is reported without probing

- **WHEN** a backend's required credentials or settings are absent
- **THEN** the system SHALL report that backend as not configured with no reachability result and SHALL NOT attempt a network probe for it

#### Scenario: Broker in stub mode is not network-probed

- **WHEN** the broker is configured to run in offline/stub mode
- **THEN** the system SHALL report the broker's mode as stub and SHALL NOT make a network call to the brokerage

### Requirement: Never expose secret values in the status report

The system SHALL NOT include any secret value — API key, secret key, or token — in the status report. Credential presence SHALL be conveyed only as a boolean (configured / key-present), and backend identifiers SHALL be limited to non-secret values such as the broker mode, the web-search provider name, and the AI model id.

#### Scenario: Report conveys configuration without secrets

- **WHEN** the system status is reported for a configured backend
- **THEN** the report SHALL indicate that the backend is configured without including any key, secret, or token value
