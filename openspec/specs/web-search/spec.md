# web-search Specification

## Purpose

Gives the recommender and AI-portfolio agents a single web-search tool whose
backend search provider is selectable by configuration, returning a normalised,
budget-capped set of trimmed results regardless of which provider is used.

## Requirements

### Requirement: Configurable web-search provider

The system SHALL expose a web-search capability to its agents whose backend
search provider is selected by configuration, supporting at least SerpAPI and
Serper. When the provider is SerpAPI the system SHALL authenticate with the
SerpAPI key; when the provider is Serper the system SHALL authenticate with the
Serper key. When the configured provider has no key set, a search SHALL fail
with a clear, provider-named error rather than silently returning nothing. When
the configured provider value is not a recognised provider, a search SHALL fail
with a clear error naming the unrecognised value. Changing the configured
provider SHALL NOT require any code change.

#### Scenario: Provider selection drives the backend

- **WHEN** the web-search provider is configured as Serper and a search runs
- **THEN** the system SHALL query the Serper backend using the Serper key, and SHALL NOT query SerpAPI

#### Scenario: SerpAPI remains available

- **WHEN** the web-search provider is configured as SerpAPI and a search runs
- **THEN** the system SHALL query the SerpAPI backend using the SerpAPI key

#### Scenario: Missing key for the selected provider

- **WHEN** a search runs while the configured provider's key is not set
- **THEN** the system SHALL fail with an error that names the missing key and SHALL NOT attempt the request

#### Scenario: Unrecognised provider value

- **WHEN** a search runs while the configured provider is an unrecognised value
- **THEN** the system SHALL fail with an error naming the unrecognised provider value

### Requirement: Normalised trimmed search results

The system SHALL return search results in a single normalised, trimmed shape
that is independent of the selected provider: a capped list of organic results
each reduced to its title, link, and snippet, plus any available answer-box and
knowledge-graph snippet, and an error field when the backend reports one.
Downstream consumers (the stored research transcript and its display) SHALL see
the same result shape regardless of which provider produced the results.

#### Scenario: Results normalised across providers

- **WHEN** either provider returns raw results for a query
- **THEN** the system SHALL return the capped organic results as title/link/snippet entries plus any answer-box and knowledge-graph snippet, in the same shape for both providers

#### Scenario: Backend error surfaced

- **WHEN** the selected provider's backend reports an error for a query
- **THEN** the system SHALL return that error in the normalised result rather than raising it to the agent

### Requirement: Provider-independent search budget and research log

The system SHALL enforce a per-run cap on the number of web searches and SHALL
record each performed search (its query, trimmed results, and any error) into
the run's research log, independently of which provider is selected. When the
per-run budget is exhausted, a further search SHALL return a budget-exhausted
result without contacting any provider.

#### Scenario: Budget exhaustion short-circuits the provider

- **WHEN** a run has exhausted its web-search budget and the agent searches again
- **THEN** the system SHALL return a budget-exhausted result without contacting the selected provider

#### Scenario: Searches recorded for the run

- **WHEN** a search is performed during a run with research recording active
- **THEN** the system SHALL append the query, trimmed results, and any error to the run's research log regardless of the selected provider
