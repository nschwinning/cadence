## Purpose

Defines how the system routes AI agent LLM calls to a model provider (OpenAI or Anthropic) through an optional proxy selected by the model identifier, and how it captures per-run token usage and cost — so a session can run on a model from either provider and operators can account for AI spend, without changing how agents are written or invoked.

## ADDED Requirements

### Requirement: Route agent LLM calls through an optional model-provider proxy

The system SHALL support directing all AI agent LLM calls through a single configured model-provider proxy endpoint, so that the provider a run executes on is determined by the run's model identifier rather than by a hard-coded provider. When a proxy endpoint is configured, the system SHALL send every agent run to that endpoint authenticated with the configured proxy credential, and the run's **model identifier** SHALL select which provider and model the proxy routes to. The system SHALL continue to select the model by identifier exactly as before — the proxy routing SHALL NOT change which model identifier a session or run uses, nor require agents to know the provider.

The supported providers SHALL be OpenAI and Anthropic only. Model identifiers in the catalog that denote OpenAI models SHALL route to OpenAI, and identifiers that denote Anthropic (Claude) models SHALL route to Anthropic.

#### Scenario: Agent run routed to its provider by model identifier

- **WHEN** the proxy endpoint is configured and an agent run executes with a catalog model identifier
- **THEN** the system SHALL send the run to the configured proxy, which routes it to the provider that owns that model identifier (OpenAI for an OpenAI model, Anthropic for a Claude model)

#### Scenario: Model selection is unchanged by routing

- **WHEN** a session is built or rebalanced with a given model identifier and the proxy is configured
- **THEN** the run SHALL execute on that same model identifier, and enabling the proxy SHALL NOT alter which model identifier the session freezes or the run records

### Requirement: Proxy routing is opt-in and disabled by default

The system SHALL treat the model-provider proxy as opt-in: it is enabled only when a proxy endpoint is configured. When no proxy endpoint is configured, the system SHALL execute agent runs exactly as it did before this capability existed — directly against the default OpenAI configuration — with no change to behavior, and offline/stubbed agent modes SHALL remain unaffected whether or not a proxy endpoint is configured.

#### Scenario: Disabled when unconfigured

- **WHEN** no proxy endpoint is configured
- **THEN** agent runs SHALL execute against the default OpenAI configuration with behavior unchanged from before this capability existed

#### Scenario: Offline mode unaffected

- **WHEN** an agent is running in its offline/stubbed mode
- **THEN** its behavior SHALL be unaffected by whether a proxy endpoint is configured, because no live LLM call is made

### Requirement: The catalog offers models from both providers

The AI model catalog SHALL be able to offer selectable models from both supported providers — OpenAI and Anthropic — each as a catalog entry with a stable identifier and a human-readable display name, selectable and persistable by a session on the same terms as any other catalog model. An Anthropic model offered in the catalog SHALL be one that supports schema-enforced structured output, so that the agent factory's mandatory structured-output contract holds for runs on that model.

#### Scenario: Catalog includes an Anthropic model

- **WHEN** a client reads the AI model catalog with Anthropic models configured
- **THEN** the catalog SHALL include at least one Anthropic (Claude) model as a selectable entry with a stable identifier and display name, selectable on the same terms as an OpenAI model

#### Scenario: Session runs on a selected Anthropic model

- **WHEN** a session is built selecting an Anthropic model from the catalog and the proxy is configured
- **THEN** the session SHALL freeze that model and its AI runs SHALL execute on it via the proxy, producing the same structured output contract the system enforces for any run

### Requirement: Capture per-run token usage and cost

When agent runs are routed through the proxy, the system SHALL capture, per LLM request, the usage and cost of the request — the model used, the token counts, and the computed cost — in a durable store, and SHALL attach to each agent run a trace identifier that allows a captured usage record to be correlated back to the Cadence run that produced it. Usage and cost SHALL be derived from the provider-reported token counts for the request. The system SHALL NOT require the agent code paths to extract or persist usage figures themselves in order for usage to be captured.

#### Scenario: Usage and cost recorded for a run

- **WHEN** an agent run is routed through the proxy and completes an LLM request
- **THEN** a usage record SHALL be captured for that request including the model, token counts, and computed cost

#### Scenario: Usage correlates to the originating run

- **WHEN** an agent run is executed through the proxy
- **THEN** the run SHALL carry a trace identifier that allows its captured usage records to be correlated back to that Cadence run

#### Scenario: No usage capture when the proxy is disabled

- **WHEN** no proxy endpoint is configured
- **THEN** the system SHALL execute runs without the proxy's usage capture and SHALL NOT fail for lack of it
