## MODIFIED Requirements

### Requirement: Normalised trimmed search results

The system SHALL return search results in a single normalised, trimmed shape
that is independent of the selected provider: a capped list of organic results
each reduced to its title, link, and snippet — plus its date when the provider
supplies one — a capped list of at most 5 top stories (the provider's news block:
SerpAPI `top_stories`, Serper `topStories`) each reduced to its title, link,
source and date, plus any available answer-box and knowledge-graph snippet, and an
error field when the backend reports one. Absent blocks SHALL be omitted.
Downstream consumers (the stored research transcript and its display) SHALL see
the same result shape regardless of which provider produced the results.

#### Scenario: Results normalised across providers

- **WHEN** either provider returns raw results for a query
- **THEN** the system SHALL return the capped organic results as title/link/snippet entries plus any answer-box and knowledge-graph snippet, in the same shape for both providers

#### Scenario: Backend error surfaced

- **WHEN** the selected provider's backend reports an error for a query
- **THEN** the system SHALL return that error in the normalised result rather than raising it to the agent

#### Scenario: Top stories kept

- **WHEN** a provider's results include a top-stories news block
- **THEN** the normalised result SHALL include up to 5 of them with title, link, source and date,
  in the same shape for both providers

#### Scenario: Result dates kept

- **WHEN** an organic result carries a date
- **THEN** the normalised organic entry SHALL include that date
