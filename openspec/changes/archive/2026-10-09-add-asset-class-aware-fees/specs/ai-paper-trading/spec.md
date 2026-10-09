## MODIFIED Requirements

### Requirement: Reserve a cash buffer when sizing orders

The AI executor SHALL reserve a **cash buffer** before sizing build or rebalance
orders, so that executed buys cannot claim the full value available and the
session's **unallocated cash is not driven negative** by fully deploying value
plus transaction fees and market-order fill slippage.

The reserved buffer SHALL be the **greater of**:

1. a **configurable percentage** of the sizing base (the allocated capital at
   build, the session's current marked-to-market value at rebalance), and
2. the **estimated transaction fees** for the run under the asset-class-aware fee
   model — **zero for equity orders**, and the **crypto fee percentage applied to
   the estimated crypto order notional** for the run (bounded above by the crypto
   fee percentage times the sizing base).

The sizing base SHALL be reduced by the reserved buffer **before** any target
weight is applied, so every per-ticker allocation is sized against the net
(post-buffer) base. The reserve SHALL be applied consistently at both the
initial build and every rebalance, and SHALL apply to a crypto-only rebalance's
crypto-scoped base as well. When the crypto fee percentage and the buffer
percentage are both zero, the reserve SHALL be zero and sizing SHALL be unchanged.

The buffer SHALL only shrink the base the executor sizes against; it SHALL NOT
change the target-weight delta model, guardrail enforcement, crypto-only
scoping, the `market_open` equity-skip, or the sells-before-buys phasing.

#### Scenario: Fully invested target leaves cash non-negative

- **WHEN** a session is rebalanced toward target weights that sum to
  approximately one
- **THEN** the executor SHALL size the target positions against the current
  value reduced by the reserved cash buffer, so that after the fees for the
  executed trades the session's unallocated cash is not negative

#### Scenario: Buffer is the greater of the percentage and the fee estimate

- **WHEN** the estimated fees for a run exceed the configured percentage of
  the sizing base
- **THEN** the executor SHALL reserve the fee estimate rather than the smaller
  percentage, and conversely SHALL reserve the percentage when it is the larger
  of the two

#### Scenario: Build reserves the buffer too

- **WHEN** a portfolio is first built
- **THEN** the executor SHALL size the initial positions against the allocated
  capital reduced by the reserved cash buffer, leaving a cash reserve rather than
  deploying the full allocated capital

#### Scenario: Zero cost and zero percentage disable the reserve

- **WHEN** the crypto fee percentage and the buffer percentage are both zero
- **THEN** the reserved buffer SHALL be zero and sizing SHALL match the behavior
  with no buffer

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
  that day, **together with the count of the day's filled orders** so the day's
  trading activity is recorded explicitly for offline learning; and
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
recorded order count being zero). On a day a session has **no value snapshot** (it
was not selected for the day), the system SHALL skip the session, recording no
learning snapshot for it.

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

## REMOVED Requirements

### Requirement: Per-trade transaction cost

### Requirement: Live session performance KPIs

## ADDED Requirements

### Requirement: Asset-class-aware transaction cost

The system SHALL charge an **asset-class-aware** transaction cost on every executed
trade it records for a paper-trading session, regardless of side (buy or sell),
matching the broker's real fee schedule: **equity (and any non-crypto) trades
SHALL incur no transaction cost**, and **crypto trades SHALL incur a fee equal to a
configurable percentage of the trade's executed notional** (the filled price, or
the quoted price when no fill price is available, times the traded quantity),
defaulting to 0.25%. The cost SHALL be applied at the single point where a trade is
recorded, so that no trade can be recorded without the correct cost being assessed,
and the system SHALL accumulate these costs per session as a cumulative,
non-negative transaction-fees total.

A session's current portfolio value SHALL be net of its cumulative transaction
fees: the value SHALL equal the allocated capital plus cumulative realised
profit/loss, minus cumulative transaction fees, plus live unrealised profit/loss
on open positions. Consequently the cash portion of the valuation and the daily
value snapshots SHALL reflect fees paid. The realised profit/loss recorded on an
individual closed position SHALL remain gross (derived from entry and exit prices
only) — transaction fees SHALL be tracked at the session level rather than folded
into per-position realised profit/loss.

When this model is first adopted, the system SHALL **restate historical fees** so
that every session's recorded fees and historical valuations reflect the new model
as if it had always applied, rather than preserving the retired flat per-trade fee:

- Each session's cumulative transaction-fees total SHALL be **recomputed** as the
  sum, over that session's recorded trades, of the asset-class-aware fee for each
  trade — **zero for equity (non-crypto) trades** and the **crypto fee percentage
  times the trade's executed notional** (its filled price when present, otherwise
  its recorded price, times its quantity) for crypto trades. A trade's asset class
  SHALL be determined from its instrument's recorded category.
- Each session's **recorded daily value snapshots SHALL be re-derived** so that the
  snapshot's portfolio value and cash reflect the recomputed (lower) cumulative fees
  as of that snapshot's date, and each snapshot's day-over-day profit and loss SHALL
  be recomputed consistently from the corrected values. A snapshot's positions value
  SHALL be unchanged. The restatement SHALL NOT re-quote prices or re-run valuation
  against the broker; it SHALL adjust the stored values by the change in cumulative
  fees only.
- The restatement SHALL be a one-time data migration that changes recorded values
  only (no table or column is added or removed), SHALL use a fixed crypto fee
  percentage captured in the migration (independent of any later change to the
  configured percentage), and SHALL be idempotent in effect (re-deriving from the
  trade ledger yields the same recomputed fees and snapshot values).

#### Scenario: Recording a trade charges the cost

- **WHEN** the system records an executed trade for a crypto asset
- **THEN** the session's cumulative transaction fees SHALL increase by the
  configured crypto fee percentage times the trade's executed notional
- **AND** a session that executes two crypto trades in a run SHALL accrue the fee
  for each

#### Scenario: Recording an equity trade charges no fee

- **WHEN** the system records an executed trade for an equity (non-crypto) asset
- **THEN** the session's cumulative transaction fees SHALL NOT increase

#### Scenario: Portfolio value is net of fees

- **WHEN** the system values a session that has accrued transaction fees
- **THEN** the reported current portfolio value SHALL subtract the session's
  cumulative transaction fees from what it would otherwise be

#### Scenario: Closed-position realised P&L stays gross

- **WHEN** a position is exited and its realised profit/loss is recorded
- **THEN** that per-position realised profit/loss SHALL be derived from entry and
  exit prices only and SHALL NOT be reduced by the transaction cost

#### Scenario: Historical fees restated under the new model

- **WHEN** the new fee model is adopted for a session that had recorded trades and
  fees under the retired flat per-trade fee
- **THEN** the session's cumulative transaction fees SHALL be recomputed to zero for
  its equity trades and the crypto fee percentage times notional for its crypto
  trades, replacing the previously accrued flat-fee total

#### Scenario: Historical value snapshots re-derived

- **WHEN** the historical fees are restated for a session that has recorded daily
  value snapshots
- **THEN** each snapshot's portfolio value and cash SHALL be increased by the
  reduction in cumulative fees as of that snapshot's date (its positions value
  unchanged), and its day-over-day profit and loss SHALL be recomputed from the
  corrected values

### Requirement: Live session performance KPI summary

The system SHALL expose, on demand for a given paper-trading session, a summary of the session's live performance comprising: the current portfolio value (net asset value: cash plus open positions valued at current market quotes, net of cumulative transaction fees), the session's **unallocated (free) cash** (the current portfolio value less the market value of open positions), cumulative realised profit/loss, live unrealised profit/loss on open positions, cumulative transaction fees paid, the **daily average orders** (defined below), total return (as both an absolute money amount and a fraction), a risk-adjusted Sharpe ratio, the benchmark it is compared against, the benchmark's total return over the same period as a fraction, and the session's excess return over the benchmark as a fraction. The **absolute total return** SHALL be the current portfolio value minus the session's contributed capital (so a capital contribution raises both equally and is not counted as a gain). The **total return fraction** SHALL be **time-weighted**: it SHALL be computed from the session's contribution-adjusted daily return series (each day's return excluding any capital contributed that day) chained across the session's life, so that capital contributed mid-session does not inflate or dilute the reported return; for a session that has had no capital increase this time-weighted fraction SHALL equal the session's simple return of current value over its single contribution. The benchmark return SHALL be the fractional return of a buy-and-hold of the benchmark from the session's start to the latest available benchmark price, derived from the stored benchmark price series, and the excess return SHALL be the session's time-weighted return fraction minus the benchmark's return fraction. When the benchmark has insufficient stored prices to compute a return the benchmark return and excess return SHALL be reported as unavailable (no value) rather than failing the request.

The **daily average orders** SHALL be the session's total number of recorded orders (executed trades) divided by the number of recorded daily value snapshots for the session. When the session has no recorded daily value snapshots the daily average orders SHALL be reported as unavailable (no value) rather than dividing by zero.

Requesting the summary SHALL value the session's open positions against current quotes at request time (marking to market on load) rather than returning a stale stored valuation. A request for an unknown session SHALL fail as not found.

#### Scenario: Summary for a session with open positions

- **WHEN** a client requests the KPI summary for an existing session
- **THEN** the system SHALL mark the session's open positions to market and return the current portfolio value (net of transaction fees), the unallocated cash, realised P&L, unrealised P&L, cumulative transaction fees, the daily average orders (or an unavailable value when the session has no snapshots), total return (absolute and time-weighted fraction), the Sharpe ratio (or an unavailable Sharpe when history is insufficient), the benchmark return, and the excess return over the benchmark

#### Scenario: Unknown session

- **WHEN** a client requests the KPI summary for a session id that does not exist
- **THEN** the system SHALL respond with a not-found error and no summary

#### Scenario: Total return relative to allocated capital

- **WHEN** the KPI summary is computed
- **THEN** the absolute total return SHALL be the current portfolio value minus the session's contributed capital (its allocated capital), and the total return fraction SHALL be the session's time-weighted return across its life

#### Scenario: Capital contribution does not inflate the time-weighted return

- **WHEN** the KPI summary is computed for a session that received a capital contribution after it started
- **THEN** the time-weighted return fraction SHALL exclude the contributed cash (the contribution SHALL NOT appear as a gain), rather than rising simply because more capital was added

#### Scenario: Time-weighted return matches simple return without contributions

- **WHEN** the KPI summary is computed for a session that has never had its capital increased
- **THEN** the time-weighted return fraction SHALL equal the session's simple return of current value over its original allocated capital

#### Scenario: Unallocated cash reported

- **WHEN** the KPI summary is computed for a session
- **THEN** the summary SHALL include the session's unallocated (free) cash as the current portfolio value less the market value of the session's open positions

#### Scenario: Benchmark and excess return reported

- **WHEN** the KPI summary is computed and the benchmark has sufficient stored prices
- **THEN** the summary SHALL include the benchmark's fractional return over the session's period and the session's excess return (the session's time-weighted return fraction minus the benchmark's return fraction)

#### Scenario: Benchmark unavailable

- **WHEN** the KPI summary is computed but the benchmark has insufficient stored prices
- **THEN** the summary SHALL report the benchmark return and excess return as unavailable rather than failing the request

#### Scenario: Cumulative transaction fees reported

- **WHEN** a client requests the KPI summary for a session that has executed trades
- **THEN** the summary SHALL include the session's cumulative transaction fees as a non-negative money amount

#### Scenario: Daily average orders reported

- **WHEN** the KPI summary is computed for a session that has at least one recorded daily value snapshot
- **THEN** the summary SHALL include the daily average orders as the session's total number of recorded orders divided by the number of recorded daily value snapshots

#### Scenario: Daily average orders without snapshots

- **WHEN** the KPI summary is computed for a session that has no recorded daily value snapshots
- **THEN** the summary SHALL report the daily average orders as unavailable rather than failing the request or dividing by zero
