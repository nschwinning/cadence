## ADDED Requirements

### Requirement: Learning feedback is a per-session opt-in frozen at build time

The system SHALL expose a per-session boolean option that controls whether the
session's rebalance agent is informed of its own recent prior-run outcomes, and a
per-session learning-window value (a number of recent days) that sets how many
recent outcomes are summarized. Both SHALL default to disabled / a configured
default window, SHALL be chosen when the session is built, and SHALL be frozen for
the life of the session — the same build-time-frozen pattern as the stop-loss and
risk-guardrail options and their parameters — so neither SHALL be changeable after
build. The window SHALL be meaningful only when learning feedback is enabled, and
when enabled without an explicit window the system SHALL apply a configured default
window. Sessions that predate these options SHALL be treated as having learning
feedback disabled, leaving their behavior unchanged. The build flow SHALL record the
chosen values on the session and SHALL NOT itself consume prior-run outcomes.

#### Scenario: Flag and window chosen at build and frozen

- **WHEN** an AI session is built with learning feedback enabled and a learning
  window
- **THEN** the session SHALL be persisted with learning feedback enabled and that
  window, and both values SHALL remain fixed for the life of the session

#### Scenario: Enabled without an explicit window uses the configured default

- **WHEN** an AI session is built with learning feedback enabled but no window
  specified
- **THEN** the session SHALL be persisted with learning feedback enabled and the
  configured default window

#### Scenario: Default and pre-existing sessions disabled

- **WHEN** an AI session is built without enabling learning feedback, or a session
  predates the option
- **THEN** learning feedback SHALL be disabled for that session and its rebalance
  prompt SHALL be unchanged from today's

### Requirement: Rebalance agent informed of recent prior-run outcomes

When a session has learning feedback enabled, the system SHALL provide that
session's rebalance agent with an advisory summary of its recent prior daily-run
outcomes, drawn from the session's consolidated daily-run learning snapshots (see
"Consolidated daily-run learning snapshot"), so the agent can take its own recent
results — and the cost of its own churn — into account when deciding the next
rebalance. The summary SHALL be built from the most recent snapshots for that
session, up to the session's frozen learning window, ordered most-recent-first, and
SHALL distill each snapshot into a compact per-day line that is **cost/churn-forward**:
it SHALL convey at least the net-of-fees realized profit/loss, the fees paid, and
the number of orders placed, followed by the end-of-day portfolio valuation; it MAY
additionally convey the day's return and notable gate/skip counts.

This summary SHALL be advisory context only: it SHALL NOT impose hard constraints
and SHALL NOT alter order sizing, risk guardrails, numeric clamps, or valuation.
Only the rebalance flow SHALL consume it. The distillation of snapshots into prompt
text SHALL be deterministic. When the session has learning feedback disabled, or
when the session has no daily-run snapshots, the rebalance prompt SHALL omit the
prior-outcomes section entirely and SHALL otherwise be unchanged.

#### Scenario: Recent outcomes included when enabled

- **WHEN** a session with learning feedback enabled and one or more daily-run
  snapshots is rebalanced
- **THEN** the rebalance prompt SHALL include an advisory section summarizing the
  most recent snapshots, up to the session's frozen window, ordered
  most-recent-first, each line leading with net-of-fees realized P&L, fees paid, and
  orders placed, followed by end-of-day valuation

#### Scenario: Disabled per session

- **WHEN** a session with learning feedback disabled is rebalanced
- **THEN** no daily-run snapshots SHALL be fetched for the prompt and the rebalance
  prompt SHALL omit the prior-outcomes section, leaving the prompt otherwise
  unchanged

#### Scenario: Window bounds the number of outcomes shown

- **WHEN** a session with learning feedback enabled has more daily-run snapshots
  than its frozen learning window
- **THEN** the prompt SHALL include only the most recent snapshots up to that
  session's window

#### Scenario: Enabled session with no snapshots

- **WHEN** a session with learning feedback enabled but no daily-run snapshots is
  rebalanced
- **THEN** the rebalance prompt SHALL omit the prior-outcomes section and SHALL
  otherwise be unchanged

#### Scenario: Advisory only, no effect on sizing or guardrails

- **WHEN** the prior-outcomes section is present in the rebalance prompt
- **THEN** it SHALL NOT change order sizing, risk guardrails, numeric clamps, or
  valuation, and the build flow SHALL NOT consume prior-run outcomes

## MODIFIED Requirements

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
  timestamp, order status, **and the transaction fee assessed on that order when it
  was recorded**, taken from the session's reconciled trade ledger for that day,
  **together with the count of the day's filled orders and the day's total
  transaction fees** so the day's trading activity and its cost are recorded
  explicitly for offline learning; and
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
valuation with the rebalancing, reasoning, indicator, and order portions absent (its
recorded order count being zero and its recorded day's total transaction fees being
zero). On a day a session has **no value snapshot** (it was not selected for the
day), the system SHALL skip the session, recording no learning snapshot for it.

Transaction fees recorded for a day SHALL be those assessed when the orders were
recorded; days whose orders predate per-order fee recording MAY report a zero or
unknown fee for those orders rather than recomputing them.

#### Scenario: Learning snapshot consolidates a day's run

- **WHEN** the assembly runs for a session that had a rebalancing run and a value
  snapshot on the day
- **THEN** the system SHALL record one learning snapshot for that session and day
  containing the run's reasoning/result, the indicator values the run used, the run's
  outcome statistics, the day's filled orders with their reconciled filled prices, and
  the day's P&L and valuation

#### Scenario: Learning snapshot records the day's order count

- **WHEN** the assembly runs for a session on a day it filled orders
- **THEN** the recorded learning snapshot SHALL include the count of the day's
  filled orders alongside the orders themselves

#### Scenario: Learning snapshot records per-order and per-day fees

- **WHEN** the assembly runs for a session on a day it filled orders that were
  recorded with their assessed transaction fees
- **THEN** the recorded learning snapshot SHALL include each filled order's assessed
  transaction fee and the day's total transaction fees

#### Scenario: Learning snapshot is idempotent per day

- **WHEN** the assembly runs twice on the same calendar day for a session
- **THEN** the system SHALL retain a single learning snapshot for that session and
  day, reflecting the latest run, rather than creating a duplicate

#### Scenario: Day with a value snapshot but no rebalancing run

- **WHEN** the assembly runs for a session that has a value snapshot for the day but
  had no rebalancing run that day
- **THEN** the system SHALL record a learning snapshot carrying the day's P&L and
  valuation with the rebalancing, reasoning, indicator, and order portions absent and
  its recorded order count being zero

#### Scenario: Day with no value snapshot is skipped

- **WHEN** the assembly runs for a session that has no value snapshot for the day
- **THEN** the system SHALL record no learning snapshot for that session

#### Scenario: Learning snapshot is not exposed to clients

- **WHEN** a client reads a session, its run history, or any paper-trading read API
- **THEN** the learning snapshot SHALL NOT appear in any response
