## ADDED Requirements

### Requirement: Rebalance agent receives run context and recent headlines

Every AI-portfolio rebalance — stock and crypto prompts, for every session whatever its frozen
prompt version and whether or not it uses news sentiment — SHALL give the agent:

- a **run-context** section appended to the rendered input (like the guardrails and recent-outcomes
  sections) stating today's date in America/New_York and research guidance: check for material
  developments of the last 7 days before keeping or adding a name; include the current month and
  year in news searches; prefer the search results' top stories; check every result's date and
  disregard results older than the period being assessed; and remember that company fiscal years
  differ from calendar years;
- for each holding and candidate, `recent_headlines`: up to `NEWS_HEADLINES_PER_TICKER` (default
  3) newest news headlines about that ticker from the last `NEWS_HEADLINES_WINDOW_DAYS` (default 3)
  days, newest first, each with its headline, source and publication time, from the configured
  news source.

A ticker with no recent headlines, or whose fetch fails, SHALL omit the field; a headline fetch
SHALL never fail the run. `NEWS_HEADLINES_PER_TICKER` of 0 SHALL disable headlines. The section and
headlines are advisory context only and SHALL NOT change sizing, guardrails or valuation.

#### Scenario: Headlines without news sentiment

- **WHEN** a session without news sentiment rebalances and a holding has three headlines from today
- **THEN** that holding SHALL carry `recent_headlines` with those three headlines, newest first,
  with their dates and sources

#### Scenario: Existing frozen session gets the run context

- **WHEN** a session frozen on an earlier prompt version rebalances
- **THEN** its input SHALL end with the run-context section naming today's date

#### Scenario: News source failure does not fail the run

- **WHEN** the news source is unreachable during a rebalance
- **THEN** no ticker SHALL carry `recent_headlines` and the rebalance SHALL proceed

#### Scenario: Headlines disabled

- **WHEN** `NEWS_HEADLINES_PER_TICKER` is 0
- **THEN** no headlines SHALL be fetched or attached
