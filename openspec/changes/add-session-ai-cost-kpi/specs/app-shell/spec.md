## ADDED Requirements

### Requirement: Session AI cost KPI tile

The session-detail performance KPI group SHALL include an "AI cost" tile that displays the session's cumulative AI cost in US dollars. When no cost value is available (the cost source is unconfigured, errored, or the session has no attributed spend), the tile SHALL render a neutral placeholder rather than a zero or an error.

#### Scenario: Tile shows the cost when available

- **WHEN** the session KPIs include an AI cost value
- **THEN** the session-detail page shows an "AI cost" tile formatted as a USD amount

#### Scenario: Tile shows a placeholder when the cost is unavailable

- **WHEN** the session KPIs carry no AI cost value
- **THEN** the "AI cost" tile renders a neutral placeholder (an em dash), not `$0.00` or an error
