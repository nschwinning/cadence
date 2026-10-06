## ADDED Requirements

### Requirement: Consolidated daily-run learning snapshot

The system SHALL maintain a backend-only learning record that consolidates, for
each AI-managed paper-trading session (portfolio), a single row per calendar day
that ties together everything needed to learn offline from that day's AI trading
decision: the day's rebalancing result, the AI's reasoning, the technical-indicator
values the agent saw, the orders that were actually filled including their filled
price, and that day's profit and loss.

Each learning snapshot SHALL be keyed by session and calendar day (`run_date`, the
same calendar day in the same timezone used by the end-of-day snapshot job) and
SHALL also carry the session's portfolio identifier so records can be grouped per
portfolio. Recording SHALL be idempotent per session per day: re-running the
assembly on the same calendar day SHALL update that day's learning snapshot rather
than create a duplicate.

Each learning snapshot SHALL consolidate, from data already persisted elsewhere
(without re-computing technical indicators or re-running the agent):

- a reference to the day's rebalancing run and its AI reasoning / result (target
  allocations, thesis, confidence, portfolio health) as produced by that run;
- the technical-indicator values handed to the agent for that run (per candidate,
  holding, and dropped candidate, including reversal flags) as recorded on the run;
- the run's outcome statistics (order counts, realized profit and loss, account
  snapshot, gate counts, and guardrail observations) as recorded on the run;
- the day's filled orders including each order's reconciled filled price, filled
  timestamp, and order status, taken from the session's reconciled trade ledger for
  that day; and
- the day's profit and loss and valuation (total value, cash value, positions
  value, absolute and percent day's P&L, and the per-position breakdown) taken from
  that day's value snapshot.

The learning snapshot SHALL be **backend-only**: it SHALL NOT be exposed through any
read schema, read API, or frontend surface, mirroring the deliberate exclusion of
the machine-readable run statistics from the run-details read model. It exists for
export and offline learning only.

On a day a session has **no rebalancing run** (for example a skipped run, a weekend,
or a stocks-only session on a non-trading day) but **does** have a value snapshot,
the system SHALL still record a learning snapshot carrying that day's P&L and
valuation with the rebalancing, reasoning, indicator, and order portions absent. On
a day a session has **no value snapshot** (it was not selected for the day), the
system SHALL skip the session, recording no learning snapshot for it.

#### Scenario: Learning snapshot consolidates a day's run

- **WHEN** the assembly runs for a session that had a rebalancing run and a value
  snapshot on the day
- **THEN** the system SHALL record one learning snapshot for that session and day
  containing the run's reasoning/result, the indicator values the run used, the run's
  outcome statistics, the day's filled orders with their reconciled filled prices, and
  the day's P&L and valuation

#### Scenario: Learning snapshot is idempotent per day

- **WHEN** the assembly runs twice on the same calendar day for a session
- **THEN** the system SHALL retain a single learning snapshot for that session and
  day, reflecting the latest run, rather than creating a duplicate

#### Scenario: Day with a value snapshot but no rebalancing run

- **WHEN** the assembly runs for a session that has a value snapshot for the day but
  had no rebalancing run that day
- **THEN** the system SHALL record a learning snapshot carrying the day's P&L and
  valuation with the rebalancing, reasoning, indicator, and order portions absent

#### Scenario: Day with no value snapshot is skipped

- **WHEN** the assembly runs for a session that has no value snapshot for the day
- **THEN** the system SHALL record no learning snapshot for that session

#### Scenario: Learning snapshot is not exposed to clients

- **WHEN** a client reads a session, its run history, or any paper-trading read API
- **THEN** the learning snapshot SHALL NOT appear in any response

### Requirement: Scheduled assembly of daily-run learning snapshots

The system SHALL provide a dedicated trigger that assembles the consolidated
daily-run learning snapshots for the day's sessions. The trigger SHALL be a
cron-guarded endpoint protected by the shared cron-token secret and SHALL reject a
request with a missing or invalid token, recording nothing.

The assembly trigger SHALL be a **separate** job from both the rebalancing run and
the end-of-day value-snapshot (P&L) job, and SHALL be sequenced to run **after** the
end-of-day value-snapshot job so that the day's value snapshot exists and the
session's orders have been reconciled (their filled prices are known) before the
learning snapshot is assembled. The scheduling cadence and ordering relative to the
P&L job are a deployment concern (the cron schedule), not enforced by this endpoint.

The assembly SHALL select the day's sessions using the same selection semantics as
the end-of-day value-snapshot job (the sessions that were eligible to be snapshotted
that day). Assembly SHALL be best-effort per session: a failure assembling one
session's learning snapshot SHALL NOT abort the batch or prevent the remaining
sessions from being recorded.

#### Scenario: Assembly runs after the P&L job with a valid token

- **WHEN** the assembly trigger is called with a valid cron token after the day's
  value-snapshot job has run
- **THEN** the system SHALL assemble and record a learning snapshot for each selected
  session that has a value snapshot for the day, reading the day's reconciled orders,
  run data, and value snapshot

#### Scenario: Invalid cron token is rejected

- **WHEN** the assembly trigger is called without a valid cron token
- **THEN** the system SHALL reject the request and record no learning snapshots

#### Scenario: One session's failure does not abort the batch

- **WHEN** assembling one session's learning snapshot fails
- **THEN** the system SHALL continue assembling the remaining sessions and record
  their learning snapshots
