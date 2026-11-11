## MODIFIED Requirements

### Requirement: Consolidated daily-run learning snapshot

The system SHALL maintain a backend-only learning record that consolidates, for
each AI-managed paper-trading session (portfolio), a single row per calendar day
that ties together everything needed to learn offline from that day's AI trading
decision: the day's rebalancing result, the AI's reasoning, the technical-indicator
values the agent saw, the other opt-in signals the agent saw, the orders that were
actually filled including their filled price, and that day's profit and loss.

Each learning snapshot SHALL be keyed by session and calendar day (`run_date`, the
same calendar day in the same timezone used by the end-of-day snapshot job) and
SHALL also carry the session's portfolio identifier so records can be grouped per
portfolio. Recording SHALL be idempotent per session per day: re-running the
assembly on the same calendar day SHALL update that day's learning snapshot rather
than create a duplicate.

Each learning snapshot SHALL consolidate, from data already persisted elsewhere
(without re-computing technical indicators, re-fetching or re-scoring any signal, or
re-running the agent):

- a reference to the day's rebalancing run and its AI reasoning / result (target
  allocations, thesis, confidence, portfolio health) as produced by that run;
- the technical-indicator values handed to the agent for that run (per candidate,
  holding, and dropped candidate, including reversal flags) as recorded on the run;
- the **set of opt-in signals that were enabled for the run** — which of the
  available signals (for example the technical-indicator trend strategy, company
  fundamentals, news sentiment, and the price-ML direction signal) were in effect
  for that session's run — so a reader can tell which signals could have influenced
  the decision;
- the **per-ticker payloads the agent was shown for each enabled opt-in signal
  beyond the technical indicators** (for example the fundamentals block, the
  news-sentiment block, and the price-ML block), per candidate and per holding (and,
  for the gated signals, per dropped candidate), taken verbatim from what the run
  recorded, **including the explicit "unavailable" marker where a signal had no
  value for an asset**, so each day's decision is attributable to the signals that
  informed it;
- the run's outcome statistics (order counts, realized profit and loss, account
  snapshot, gate counts, and guardrail observations) as recorded on the run;
- the day's filled orders including each order's reconciled filled price, filled
  timestamp, order status, and the transaction fee assessed on that order when it
  was recorded, taken from the session's reconciled trade ledger for that day,
  together with the count of the day's filled orders and the day's total
  transaction fees so the day's trading activity and its cost are recorded
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
valuation with the rebalancing, reasoning, indicator, signal, and order portions
absent (its recorded order count being zero and its recorded day's total transaction
fees being zero). On a day a session has **no value snapshot** (it was not selected
for the day), the system SHALL skip the session, recording no learning snapshot for
it.

Transaction fees recorded for a day SHALL be those assessed when the orders were
recorded; days whose orders predate per-order fee recording MAY report a zero or
unknown fee for those orders rather than recomputing them.

A run that enabled no opt-in signals beyond none at all, or that predates a given
signal, SHALL simply omit that signal from the recorded enabled set and its per-ticker
payloads rather than causing an error, so older snapshots and signal-free runs remain
valid.

#### Scenario: Learning snapshot consolidates a day's run

- **WHEN** the assembly runs for a session that had a rebalancing run and a value
  snapshot on the day
- **THEN** the system SHALL record one learning snapshot for that session and day
  containing the run's reasoning/result, the indicator values the run used, the run's
  outcome statistics, the day's filled orders with their reconciled filled prices, and
  the day's P&L and valuation

#### Scenario: Learning snapshot records the enabled signal set

- **WHEN** the assembly runs for a session whose run had one or more opt-in signals
  enabled
- **THEN** the recorded learning snapshot SHALL include the set of opt-in signals that
  were enabled for that run

#### Scenario: Learning snapshot records the per-ticker signal payloads

- **WHEN** the assembly runs for a session whose run attached opt-in signal blocks
  (beyond the technical indicators) to its candidates and holdings
- **THEN** the recorded learning snapshot SHALL include, per ticker, the signal payloads
  the agent was shown for each enabled signal, taken verbatim from what the run recorded

#### Scenario: Unavailable signal value is recorded as unavailable

- **WHEN** the assembly runs for a session whose run showed a signal as "unavailable"
  for an asset
- **THEN** the recorded learning snapshot SHALL preserve that "unavailable" marker for
  that asset rather than inventing a value or omitting the asset

#### Scenario: Run predating a signal omits it

- **WHEN** the assembly runs for a session whose run enabled no opt-in signals, or
  predates a given signal
- **THEN** the system SHALL record the snapshot with that signal omitted from the enabled
  set and per-ticker payloads rather than failing

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
  valuation with the rebalancing, reasoning, indicator, signal, and order portions absent
  and its recorded order count being zero

#### Scenario: Day with no value snapshot is skipped

- **WHEN** the assembly runs for a session that has no value snapshot for the day
- **THEN** the system SHALL record no learning snapshot for that session

#### Scenario: Learning snapshot is not exposed to clients

- **WHEN** a client reads a session, its run history, or any paper-trading read API
- **THEN** the learning snapshot SHALL NOT appear in any response
