## ADDED Requirements

### Requirement: Value equity positions at the last official close when the market is closed

The system SHALL value a session's open **equity** positions at the **last official
daily close** whenever the equity market is closed, rather than at a live intraday
quote, so that a session's valuation does not drift while the market it trades in is
closed. The last official close SHALL be the most recent completed daily close on or
before the valuation day (for a weekend or a market holiday, the prior trading day's
close). **Crypto** positions SHALL always be valued at their current live price,
because crypto trades around the clock.

Whether the equity market is open SHALL be determined from the broker's market clock,
the same signal that governs weekend/holiday equity trading. When the equity market
is **open**, equity positions SHALL continue to be valued at current live quotes as
before.

This marking rule SHALL apply uniformly wherever this specification requires a
session's open positions to be "marked to market" or valued at "current market
quotes" — specifically the end-of-day value snapshot, the live session performance
KPI summary, the session's P&L and return reads, automated rebalance sizing against
the session's current marked-to-market value, and the consolidated daily-run learning
snapshot — so that every valuation path reports the same closed-market value.

When the equity market is closed and an equity position's last official close cannot
be obtained, the system SHALL fall back to its existing valuation fallbacks (a live
quote if available, otherwise the position's average cost) rather than failing the
valuation.

Because equity positions are held flat at the last official close while the market is
closed, a session that holds only equities SHALL report no day-over-day value change
across a non-trading day (for example a weekend), rather than appearing to gain or
lose from live-quote drift.

#### Scenario: Equities valued at the last official close while the market is closed

- **WHEN** a session's value is computed while the equity market is closed and the
  session holds equity positions
- **THEN** the system SHALL mark those equity positions to their last official daily
  close rather than a live intraday quote

#### Scenario: Crypto still valued live while the equity market is closed

- **WHEN** a session's value is computed while the equity market is closed and the
  session holds crypto positions
- **THEN** the system SHALL value those crypto positions at their current live price,
  not at a stale close

#### Scenario: Equities valued live while the market is open

- **WHEN** a session's value is computed while the equity market is open
- **THEN** the system SHALL value its open equity positions at current live quotes,
  unchanged from prior behavior

#### Scenario: Stocks-only session is flat across a non-trading day

- **WHEN** a stocks-only session is valued on a non-trading day (for example a
  Saturday) and again on the following trading-day marks
- **THEN** its equity value on the non-trading day SHALL equal the last official
  close, so it reports no day-over-day change attributable to live-quote drift

#### Scenario: Close unavailable falls back without failing

- **WHEN** the equity market is closed and an equity position's last official close
  cannot be obtained
- **THEN** the system SHALL fall back to a live quote if available, otherwise the
  position's average cost, rather than failing the valuation

## MODIFIED Requirements

### Requirement: Snapshot session portfolio value at end of day

The system SHALL, on a scheduled end-of-day trigger, record one portfolio-value
snapshot per active AI-managed session **selected for the day** (a session whose
strategy is AI-managed and whose status is active) and send a daily
profit-and-loss report. On a **weekday** (Monday–Friday) the selected sessions SHALL
be all active AI-managed sessions. On a **weekend day** (Saturday or Sunday,
determined by calendar in the snapshot timezone, ignoring market holidays) the
selected sessions SHALL be only those that **currently hold at least one crypto
position**; an active AI-managed session that holds no crypto position SHALL be
skipped entirely on a weekend — neither a snapshot recorded nor a notification sent.
Weekend selection SHALL be determined from the session's actual open holdings, not
from its configured asset scope, so that a session configured to allow crypto but
currently holding none is skipped on a weekend just as a stocks-only session is. The
trigger SHALL be a cron-guarded endpoint protected by the shared cron-token secret,
and SHALL reject a request with a missing or invalid token. Recording SHALL be
idempotent per session per day: re-running the trigger on the same calendar day SHALL
update that day's snapshot rather than create a duplicate.

The end-of-day snapshot and its P&L report are intended to run on **every calendar
day, including weekends**, so that a session's value and profit and loss are recorded
and reported on days its holdings move — notably its crypto sleeve, which trades
around the clock and is rebalanced on weekends. On weekends the trigger SHALL record
and report only for sessions that **currently hold crypto**, since a session holding
no crypto does not move while the equity market is closed. The trigger SHALL operate
on any day it is validly called, with no dependence on the equity market being open;
the scheduling cadence itself is a deployment concern (the cron schedule), not
enforced by this endpoint.

Each snapshot SHALL record the session's total value, its cash value, the market
value of its held positions, the day's profit and loss (absolute and percent), and a
per-position breakdown (per held ticker: quantity, price, market value, unrealized
profit and loss, and return). A session's total value SHALL be computed by marking its
open positions — taken from the session's position ledger — to market (valuing equity
positions at the last official close when the equity market is closed, per "Value
equity positions at the last official close when the market is closed") and combining
them with the session's contributed capital and realized profit and loss. The day's
profit and loss SHALL be measured against the
session's most recent prior snapshot, or against its contributed capital at the start
when no prior snapshot exists, and SHALL exclude any capital contribution recorded for
that same day — a day on which capital is added SHALL NOT report that added cash as a
day's gain. A session holding no positions SHALL record an all-cash snapshot.

The report SHALL contain, for each session snapshotted, a line with the session's
total value and the day's profit and loss (absolute and percent), the session's
benchmark and the session's return versus that benchmark (the benchmark's return over
the session's period and the session's excess return), plus the session's single
best-performing and single worst-performing individual holding ranked by their
**daily price change** — the change in a holding's price since the session's most
recent earlier value snapshot (`current snapshot price ÷ previous snapshot price −
1`). Because this daily price change is a property of the asset's price move over the
day and not of any session's cost basis, the same ticker SHALL read identically in
every session's report on a given day. This best/worst figure is the **day's** price
move and SHALL NOT be the holding's since-entry return (price versus the session's
average cost). A holding SHALL be excluded from the best/worst ranking when the
session has no earlier snapshot to compare against, when the holding did not appear in
that earlier snapshot (for example a position first opened that day), or when its
earlier price is missing or not positive; when no held asset remains comparable the
best/worst line SHALL be omitted from that session's report. When a session's
benchmark comparison is
unavailable, its line SHALL still be reported without the benchmark figures. A failure
to deliver the report SHALL NOT fail the snapshot job.

#### Scenario: Daily snapshot recorded for active AI sessions

- **WHEN** the end-of-day snapshot trigger runs on a weekday with a valid cron token
- **THEN** the system SHALL record a value snapshot for each active AI-managed
  session and SHALL NOT record snapshots for paused, stopped, or non-AI sessions

#### Scenario: Snapshot and report run on weekends

- **WHEN** the end-of-day snapshot trigger runs on a weekend (a day the equity
  market is closed) and a session currently holds at least one crypto position
- **THEN** the system SHALL record a value snapshot for that session and send the
  daily P&L report, marking crypto to its live price and any equity holdings to their
  last official close, without requiring the equity market to be open

#### Scenario: Weekend skips stocks-only sessions entirely

- **WHEN** the end-of-day snapshot trigger runs on a weekend and a session holds no
  crypto position (for example a stocks-only session)
- **THEN** the system SHALL skip that session entirely — recording no snapshot and
  sending no notification for it

#### Scenario: Weekend skips a crypto-allowed session that holds no crypto

- **WHEN** the end-of-day snapshot trigger runs on a weekend and a session is
  configured to allow crypto (scope crypto or both, or no persisted scope) but
  currently holds no crypto position
- **THEN** the system SHALL skip that session entirely on that weekend, because
  weekend selection is determined by actual crypto holdings rather than configured
  scope

#### Scenario: Snapshot is idempotent per day

- **WHEN** the snapshot trigger runs twice on the same calendar day for a session
- **THEN** the system SHALL retain a single snapshot for that session and day,
  reflecting the latest run, rather than creating a duplicate

#### Scenario: Daily P&L baseline

- **WHEN** a snapshot is recorded for a session that has a prior snapshot
- **THEN** the day's profit and loss SHALL be the change in total value since the
  prior snapshot; **AND WHEN** the session has no prior snapshot, the day's profit
  and loss SHALL be measured against the session's contributed capital

#### Scenario: Capital contributed on a snapshot day is not counted as a gain

- **WHEN** a snapshot is recorded for a session on a day that session received a capital contribution
- **THEN** the day's profit and loss SHALL exclude the contributed amount, so adding capital does not appear as a day's gain

#### Scenario: Daily report summarizes P&L and extremes

- **WHEN** the snapshot job completes and a session is snapshotted with at least one
  held asset that has a comparable earlier-snapshot price
- **THEN** the system SHALL send that session's report line showing value, P&L, and
  the session's return versus its benchmark, and SHALL include that session's best-
  and worst-performing individual holding ranked by each holding's daily price change

#### Scenario: Best/worst holding reflects the day's price move, not cost basis

- **WHEN** two different sessions each hold the same ticker at a different average
  cost and both are snapshotted on the same day with that ticker having an
  earlier-snapshot price
- **THEN** that ticker's reported daily price change SHALL be identical in both
  sessions' reports (computed from the current versus previous snapshot price), and
  SHALL NOT differ by each session's cost basis

#### Scenario: First report for a session omits the best/worst line

- **WHEN** a session is snapshotted and has no earlier value snapshot to compare
  against (its first daily report)
- **THEN** the session's report line SHALL be sent without a best/worst holding line

#### Scenario: Holding without a comparable prior price is excluded

- **WHEN** a session is snapshotted and a held asset did not appear in the session's
  most recent earlier snapshot, or its earlier price is missing or not positive
- **THEN** that asset SHALL be excluded from the best/worst ranking while other
  holdings with a comparable earlier price are still ranked, and when no held asset
  remains comparable the best/worst line SHALL be omitted from that session's report

#### Scenario: Benchmark comparison unavailable in the report

- **WHEN** a snapshotted session's benchmark comparison cannot be computed
- **THEN** the session's report line SHALL still be included without the benchmark figures

#### Scenario: Report delivery failure does not fail the job

- **WHEN** report delivery fails
- **THEN** the snapshot job SHALL still complete and the recorded snapshots SHALL
  remain persisted

#### Scenario: Invalid cron token is rejected

- **WHEN** the snapshot trigger is called without a valid cron token
- **THEN** the system SHALL reject the request and record no snapshots
