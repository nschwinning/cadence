## MODIFIED Requirements

### Requirement: Report the status of connected backends

The system SHALL expose a read-only operation that reports the current status of each external backend the application depends on: the **broker** (Alpaca), the **web-search provider**, the **market-data provider** (yfinance), the **AI model provider** (OpenAI), and the **model gateway** (the optional LiteLLM proxy). For each backend the report SHALL include: a stable backend name; whether the backend is **configured** (its required credentials/settings are present); a non-secret **identifier** describing how it is set up (for the broker its mode — paper, live, or stub; for web search the active provider name; for the AI model the configured model id; for the model gateway the non-secret proxy base URL); whether it is **reachable** (the result of a live probe, or absent when no probe was performed); the probe **latency** in milliseconds when a probe was performed; and a short human-readable **detail** message (for example an error summary) when relevant. The operation SHALL require no request body and SHALL NOT be guarded by the cron-token secret.

The model-gateway backend is opt-in and disabled by default: when no proxy base URL is configured, the system SHALL report it as not configured with no reachability result and SHALL NOT probe it. When a proxy base URL is configured, the system SHALL probe the gateway's unauthenticated liveness endpoint (sending no proxy credential) and report it reachable or unreachable accordingly, so that after the proxy is deployed and the base URL is set the status report shows the gateway connected.

#### Scenario: Report lists every backend

- **WHEN** a client requests the system status
- **THEN** the system SHALL return one status entry for each of the broker, web-search provider, market-data provider, AI model provider, and model gateway, each with its name, configured flag, non-secret identifier, reachable result, latency, and optional detail

#### Scenario: Model gateway reports connected once configured

- **WHEN** a client requests the system status and the model-gateway proxy base URL is configured and its liveness endpoint responds
- **THEN** the system SHALL report the model gateway as configured and reachable, with the non-secret proxy base URL as its identifier

#### Scenario: Model gateway is not probed when disabled

- **WHEN** a client requests the system status and no model-gateway proxy base URL is configured
- **THEN** the system SHALL report the model gateway as not configured with no reachability result and SHALL NOT make any network call for it
