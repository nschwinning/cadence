## ADDED Requirements

### Requirement: Per-portfolio AI cost breakdown

The dashboard SHALL expose an endpoint that returns the **all-time cumulative** AI (LLM)
cost **per paper-trading portfolio**, together with a grand total across those portfolios.

The breakdown SHALL cover all **active** paper-trading sessions (stopped and archived
sessions are excluded) and SHALL be **independent of** the dashboard range selector — the
figures are cumulative since each session began, not scoped to any range.

Each portfolio row SHALL carry the session identifier, the portfolio display label, and
the session's cumulative AI cost. Cost SHALL be sourced from the same LiteLLM `SpendLogs`
data as the per-session AI cost tile (summing `spend` by the `cadence_session_id`
metadata key), aggregated in a **single batched query** rather than one query per session.

When the cost source is unconfigured or unavailable, cost SHALL degrade to a null value
(never a fabricated `0` and never an error): the endpoint SHALL still return the portfolio
rows with a null cost, and the total SHALL be null when no portfolio has a readable cost.
A session that simply has no recorded spend SHALL read as `0`, distinct from the
unavailable (null) state.

#### Scenario: Breakdown lists every active portfolio's all-time cost with a total
- **WHEN** a client requests the AI cost breakdown and the cost source is reachable
- **THEN** the response includes one row per active paper-trading session with its
  portfolio label and cumulative AI cost
- **AND** a grand total equal to the sum of the per-portfolio costs

#### Scenario: Stopped and archived sessions are excluded
- **WHEN** a session is stopped or archived
- **THEN** it does not appear in the breakdown rows and its cost is not in the total

#### Scenario: Cost is aggregated in a single query, not per session
- **WHEN** the breakdown is computed for N sessions
- **THEN** the cumulative costs are read with a single grouped query over `SpendLogs`
  keyed by `cadence_session_id`, not one query per session

#### Scenario: A session with no recorded spend reads as zero
- **WHEN** a session has no matching `SpendLogs` rows but the cost source is reachable
- **THEN** that portfolio's cost is `0`, distinct from the unavailable state

#### Scenario: Cost source unavailable degrades to null without error
- **WHEN** the LiteLLM cost source is unconfigured or a query against it fails
- **THEN** the endpoint still returns the portfolio rows with a null cost and a null total
- **AND** the request does not fail

#### Scenario: Breakdown ignores the dashboard range
- **WHEN** a client requests the AI cost breakdown
- **THEN** the returned costs are all-time cumulative and do not change with any dashboard
  range selection
