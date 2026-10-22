## ADDED Requirements

### Requirement: Attribute portfolio-scoped AI spend to its session

A rebalance or initial-allocation run SHALL tag the LLM spend it generates with the originating paper-trading session and its portfolio, so the proxy's spend record can be attributed to that session. Runs that are not portfolio-scoped (the global recommender and universe-evaluation runs) SHALL NOT be attributed to any session or portfolio.

#### Scenario: Rebalance run tags its spend with the session and portfolio

- **WHEN** a rebalance (or initial-allocation) run executes while the model gateway is enabled
- **THEN** the spend recorded by the proxy for that run carries the session id and portfolio id (alongside the run trace id) as structured metadata

#### Scenario: Global runs are not attributed to a portfolio

- **WHEN** a recommender or universe-evaluation run executes
- **THEN** its spend is NOT tagged with any session id or portfolio id

#### Scenario: Attribution is inert when the gateway is disabled

- **WHEN** the model gateway is disabled (no proxy configured)
- **THEN** a rebalance run proceeds unchanged and stamps no spend metadata

### Requirement: Per-session AI cost KPI

The session performance KPIs SHALL include a cumulative AI cost in US dollars for the session, summed from the authoritative per-request cost recorded by the model proxy for that session's attributed runs. The cost source SHALL be configurable and optional: the KPI is a best-effort read that never prevents the other session KPIs from being computed.

#### Scenario: Cost reported when the source is configured and has spend

- **WHEN** the cost source is configured and the proxy has recorded spend attributed to the session
- **THEN** the session KPIs report `ai_cost_usd` as the sum of that attributed spend in USD

#### Scenario: No cost when the source is unconfigured

- **WHEN** the cost source is not configured
- **THEN** the session KPIs report `ai_cost_usd` as absent (no value), and all other KPIs are computed normally

#### Scenario: No cost when the session has no attributed spend

- **WHEN** the cost source is configured but no spend is attributed to the session yet
- **THEN** the session KPIs report `ai_cost_usd` as absent (no value)

#### Scenario: Cost read failure does not break the KPIs

- **WHEN** reading the cost source raises an error (e.g. the spend table is absent or unreachable)
- **THEN** the session KPIs report `ai_cost_usd` as absent (no value) and every other KPI is still returned

#### Scenario: Cost source connection string is never exposed

- **WHEN** session data or system status is returned to a client
- **THEN** the cost-source connection string is never included in any response
