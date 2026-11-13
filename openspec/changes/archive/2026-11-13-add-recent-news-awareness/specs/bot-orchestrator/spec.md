## ADDED Requirements

### Requirement: Orchestrator researches recent developments

The orchestrator agent's instructions SHALL direct it, when it searches the web, to look for
material developments of the last 7 days relative to the briefing's date (for example management
changes, investigations, guidance changes, mergers), to include the current month and year in news
searches, to prefer the search results' top stories, to check each result's date and disregard
stale results, and to remember that company fiscal years differ from calendar years.

#### Scenario: Instructions carry the research guidance

- **WHEN** an orchestrator run builds its agent
- **THEN** the instructions SHALL contain the recent-developments research guidance and the run
  SHALL record the prompt version that includes it
