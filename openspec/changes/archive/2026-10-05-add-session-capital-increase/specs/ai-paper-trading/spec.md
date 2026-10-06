## ADDED Requirements

### Requirement: Increase a session's capital and record it as a contribution

The system SHALL let a client increase a running paper-trading session's capital by a positive amount, and SHALL record every capital contribution to a session (its amount and effective date) so the session's return analytics can distinguish invested growth from added cash. A session's **contributed capital** SHALL be the sum of all its recorded contributions; the session's original build-time allocated capital SHALL be treated as its first contribution (an existing session with no explicitly recorded contributions SHALL be treated as a single contribution equal to its allocated capital on its start date). Increasing a session's capital SHALL record a new contribution for the increase amount, raise the session's contributed capital by that amount, and make the added amount available as investable cash — so that the next rebalance can deploy it — without itself buying or selling any position. A client SHALL be able to read a session's contributed capital. Increasing capital SHALL be increase-only: a request with a non-positive amount SHALL be rejected, and no operation SHALL decrease a session's capital or withdraw funds. A request to increase the capital of an unknown session SHALL fail as not found.

#### Scenario: Increase a session's capital

- **WHEN** a client requests to increase an existing session's capital by a positive amount
- **THEN** the system SHALL record a capital contribution for that amount, raise the session's contributed capital by the amount, and increase the session's investable cash by the amount without buying or selling any position

#### Scenario: Added capital becomes investable

- **WHEN** a session's capital has been increased and the session's next rebalance runs
- **THEN** the rebalance SHALL size against the session's current value, which now includes the added cash, so the contribution can be deployed into holdings

#### Scenario: Non-positive increase rejected

- **WHEN** a client requests a capital increase of zero or a negative amount
- **THEN** the system SHALL reject the request and SHALL NOT change the session's capital or record a contribution

#### Scenario: Increase for an unknown session

- **WHEN** a client requests a capital increase for a session id that does not exist
- **THEN** the system SHALL respond with a not-found error and record no contribution

#### Scenario: Original capital is the first contribution

- **WHEN** a session's contributed capital is read and the session has no explicitly recorded contributions
- **THEN** the system SHALL treat the session's allocated capital as a single contribution on the session's start date, so its contributed capital equals its allocated capital

## MODIFIED Requirements

### Requirement: Read paper-trading session data

The system SHALL let a client list paper-trading sessions and read a session's trades, runs, positions, its AI-portfolio events, and its daily portfolio-value snapshots. A session returned to a client SHALL include the name of the portfolio it trades so the client can identify the session by portfolio; when the portfolio cannot be resolved the name SHALL be absent (null) rather than causing an error. A session returned to a client SHALL include the benchmark it is compared against. A session returned to a client SHALL include its asset scope — whether it trades stocks only, crypto only, or both. A session returned to a client SHALL include its stop-loss configuration: whether the automatic stop-loss is enabled and, when enabled, its threshold percentage. A session returned to a client SHALL include its risk-guardrail configuration: whether the risk guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage. A session returned to a client SHALL include its contributed capital (the sum of its recorded capital contributions, equal to its allocated capital). An AI-portfolio event returned to a client SHALL include the AI's reasoning output and its persisted research transcript. A trade, closed position, or run returned to a client SHALL include the reference to the AI-portfolio event that produced it, when present. A session's value history SHALL be returned ordered oldest snapshot first, and each snapshot in the returned history SHALL carry the value of a buy-and-hold of the benchmark that receives the session's capital contributions on their effective dates — each contribution buying benchmark units at that date's benchmark price — so the benchmark line starts at the session's first contribution on the first snapshot date and steps up by each later contribution; for a session with a single contribution this is equivalent to a buy-and-hold of the allocated capital rebased to the first snapshot date. When the benchmark has no stored price on or before a snapshot's date, that snapshot's benchmark value SHALL be absent (null) rather than causing an error.

Each of a session's tabular list reads — its trades, runs, closed positions, and AI-portfolio events — SHALL support paging via a caller-supplied page size (limit) and a zero-based offset, returning at most the page size of rows starting at the offset within the read's existing ordering, together with the total number of rows recorded for that session and list. The AI-portfolio event read SHALL return its rows wrapped together with that total, in the same shape as the trades, runs, and closed-position reads (rather than a bare list without a total). Reads that source data for computed metrics rather than for a table — such as the closed-position profit-and-loss series behind the session KPIs — SHALL remain unpaged.

#### Scenario: Inspect a session

- **WHEN** a client requests a session's trades, runs, positions, or events
- **THEN** the system SHALL return the recorded data for that session

#### Scenario: Session identifies its portfolio

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include the name of the portfolio it trades

#### Scenario: Session reports its benchmark

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include the benchmark it is compared against

#### Scenario: Session reports its asset scope

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include its asset scope (stocks, crypto, or both), defaulting to both when no explicit scope was recorded

#### Scenario: Session reports its stop-loss configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its automatic stop-loss is enabled and, when enabled, its threshold percentage

#### Scenario: Session reports its guardrail configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its risk guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage

#### Scenario: Session reports its contributed capital

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include its contributed capital, equal to the sum of its recorded capital contributions (its allocated capital)

#### Scenario: Event includes reasoning and research

- **WHEN** a client reads an AI-portfolio event
- **THEN** the returned event SHALL include the AI reasoning output and the persisted research transcript

#### Scenario: Run reports its producing AI event

- **WHEN** a client reads a session's runs
- **THEN** each returned run SHALL include the reference to the AI-portfolio event that produced it when present, and SHALL omit it (null) for runs not produced by an AI build or rebalance

#### Scenario: Read a page of a session's list

- **WHEN** a client requests a session's trades, runs, closed positions, or AI-portfolio events with a page size and an offset
- **THEN** the system SHALL return at most that many rows starting at the given offset within the read's existing ordering, together with the total number of rows recorded for that session and list

#### Scenario: Event read reports its total

- **WHEN** a client reads a session's AI-portfolio events
- **THEN** the response SHALL contain the requested page of events wrapped together with the total number of events recorded for that session

#### Scenario: Offset beyond the end returns an empty page with the true total

- **WHEN** a client requests a page whose offset is at or beyond the number of recorded rows for one of these lists
- **THEN** the system SHALL return an empty page of rows together with the true total for that session and list

#### Scenario: Read session value history

- **WHEN** a client requests a session's value history
- **THEN** the system SHALL return the session's daily value snapshots ordered oldest first, each with its date, total value, cash value, positions value, day's profit and loss, and the contribution-aware rebased benchmark value as of that date

#### Scenario: Benchmark line reflects a later capital contribution

- **WHEN** a client requests the value history of a session that received a capital contribution after it started
- **THEN** each snapshot's benchmark value on or after the contribution's effective date SHALL include benchmark units bought with the contributed amount at that date's benchmark price, so the benchmark line steps up by the contribution rather than ignoring it

#### Scenario: Benchmark price missing for a date

- **WHEN** a client requests a session's value history and the benchmark has no stored price on or before a snapshot's date
- **THEN** the system SHALL return that snapshot with the benchmark value absent rather than failing the request

### Requirement: Snapshot session portfolio value at end of day

The system SHALL, on a scheduled end-of-day trigger, record one portfolio-value
snapshot per active AI-managed session **selected for the day** (a session whose
strategy is AI-managed and whose status is active) and send a daily
profit-and-loss report. On a **weekday** (Monday–Friday) the selected sessions SHALL
be all active AI-managed sessions. On a **weekend day** (Saturday or Sunday,
determined by calendar in the snapshot timezone, ignoring market holidays) the
selected sessions SHALL be only those whose **configured asset scope includes crypto**
(scope is crypto or both); an active AI-managed session configured stocks-only SHALL
be skipped entirely on a weekend — neither a snapshot recorded nor a notification
sent. A session with no persisted scope SHALL be treated as the default scope (both)
and is therefore included on weekends. The trigger SHALL be a cron-guarded endpoint
protected by the shared cron-token secret, and SHALL reject a request with a missing
or invalid token. Recording SHALL be idempotent per session per day: re-running the
trigger on the same calendar day SHALL update that day's snapshot rather than create a
duplicate.

The end-of-day snapshot and its P&L report are intended to run on **every calendar
day, including weekends**, so that a session's value and profit and loss are recorded
and reported on days its holdings move — notably its crypto sleeve, which trades
around the clock and is rebalanced on weekends. On weekends the trigger SHALL record
and report only for sessions whose configured scope includes crypto, since a
stocks-only session's holdings do not move while the equity market is closed. The
trigger SHALL operate on any day it is validly called, with no dependence on the equity
market being open; the scheduling cadence itself is a deployment concern (the cron
schedule), not enforced by this endpoint.

Each snapshot SHALL record the session's total value, its cash value, the market
value of its held positions, the day's profit and loss (absolute and percent), and a
per-position breakdown (per held ticker: quantity, price, market value, unrealized
profit and loss, and return). A session's total value SHALL be computed by marking its
open positions — taken from the session's position ledger — to market and combining
them with the session's contributed capital and realized profit and loss. The day's
profit and loss SHALL be measured against the
session's most recent prior snapshot, or against its contributed capital at the start
when no prior snapshot exists, and SHALL exclude any capital contribution recorded for
that same day — a day on which capital is added SHALL NOT report that added cash as a
day's gain. A session holding no positions SHALL record an all-cash snapshot.

The report SHALL contain, for each session snapshotted, a line with the session's
total value and the day's profit and loss (absolute and percent), the session's
benchmark and the session's return versus that benchmark (the benchmark's return over
the session's period and the session's excess return), plus the single
best-performing and single worst-performing individual holding ranked by return
across all snapshotted sessions. When a session's benchmark comparison is
unavailable, its line SHALL still be reported without the benchmark figures. A failure
to deliver the report SHALL NOT fail the snapshot job.

#### Scenario: Daily snapshot recorded for active AI sessions

- **WHEN** the end-of-day snapshot trigger runs on a weekday with a valid cron token
- **THEN** the system SHALL record a value snapshot for each active AI-managed
  session and SHALL NOT record snapshots for paused, stopped, or non-AI sessions

#### Scenario: Snapshot and report run on weekends

- **WHEN** the end-of-day snapshot trigger runs on a weekend (a day the equity
  market is closed) and a session's configured scope includes crypto
- **THEN** the system SHALL record a value snapshot for that session and send the
  daily P&L report, marking crypto and other holdings to market, without requiring the
  equity market to be open

#### Scenario: Weekend skips stocks-only sessions entirely

- **WHEN** the end-of-day snapshot trigger runs on a weekend and a session's
  configured scope does not include crypto (stocks only)
- **THEN** the system SHALL skip that session entirely — recording no snapshot and
  sending no notification for it

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

- **WHEN** the snapshot job completes with at least one session snapshotted
- **THEN** the system SHALL send a report with a per-session line showing value,
  P&L, and the session's return versus its benchmark, and with the best- and
  worst-performing individual holding across the snapshotted sessions

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

### Requirement: Live session performance KPIs

The system SHALL expose, on demand for a given paper-trading session, a summary of the session's live performance comprising: the current portfolio value (net asset value: cash plus open positions valued at current market quotes, net of cumulative transaction fees), the session's **unallocated (free) cash** (the current portfolio value less the market value of open positions), cumulative realised profit/loss, live unrealised profit/loss on open positions, cumulative transaction fees paid, the **daily average transaction cost** (defined below), total return (as both an absolute money amount and a fraction), a risk-adjusted Sharpe ratio, the benchmark it is compared against, the benchmark's total return over the same period as a fraction, and the session's excess return over the benchmark as a fraction. The **absolute total return** SHALL be the current portfolio value minus the session's contributed capital (so a capital contribution raises both equally and is not counted as a gain). The **total return fraction** SHALL be **time-weighted**: it SHALL be computed from the session's contribution-adjusted daily return series (each day's return excluding any capital contributed that day) chained across the session's life, so that capital contributed mid-session does not inflate or dilute the reported return; for a session that has had no capital increase this time-weighted fraction SHALL equal the session's simple return of current value over its single contribution. The benchmark return SHALL be the fractional return of a buy-and-hold of the benchmark from the session's start to the latest available benchmark price, derived from the stored benchmark price series, and the excess return SHALL be the session's time-weighted return fraction minus the benchmark's return fraction. When the benchmark has insufficient stored prices to compute a return the benchmark return and excess return SHALL be reported as unavailable (no value) rather than failing the request.

The **daily average transaction cost** SHALL be the session's cumulative transaction fees divided by the number of recorded daily value snapshots for the session. When the session has no recorded daily value snapshots the daily average transaction cost SHALL be reported as unavailable (no value) rather than dividing by zero.

Requesting the summary SHALL value the session's open positions against current quotes at request time (marking to market on load) rather than returning a stale stored valuation. A request for an unknown session SHALL fail as not found.

#### Scenario: Summary for a session with open positions

- **WHEN** a client requests the KPI summary for an existing session
- **THEN** the system SHALL mark the session's open positions to market and return the current portfolio value (net of transaction fees), the unallocated cash, realised P&L, unrealised P&L, cumulative transaction fees, the daily average transaction cost (or an unavailable value when the session has no snapshots), total return (absolute and time-weighted fraction), the Sharpe ratio (or an unavailable Sharpe when history is insufficient), the benchmark return, and the excess return over the benchmark

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

#### Scenario: Daily average transaction cost reported

- **WHEN** the KPI summary is computed for a session that has at least one recorded daily value snapshot
- **THEN** the summary SHALL include the daily average transaction cost as the cumulative transaction fees divided by the number of recorded daily value snapshots

#### Scenario: Daily average transaction cost without snapshots

- **WHEN** the KPI summary is computed for a session that has no recorded daily value snapshots
- **THEN** the summary SHALL report the daily average transaction cost as unavailable rather than failing the request or dividing by zero

### Requirement: Sharpe ratio from the session's daily NAV series

The system SHALL compute a session's Sharpe ratio from the session's own ordered series of daily net-asset-value returns (the recorded daily value snapshots), **adjusted so that a day on which capital was contributed excludes the contributed amount from that day's return** (the contribution is not treated as a gain), as the mean daily return in excess of a configurable risk-free rate (defaulting to zero) divided by the standard deviation of daily returns, annualised by the square root of a configurable number of trading days per year. The Sharpe ratio SHALL be reported as unavailable (no value) when the session has fewer than a configured minimum number of daily returns, or when the daily returns have zero standard deviation. The computation SHALL rely solely on the session's recorded daily NAV series and its recorded capital contributions and SHALL NOT fetch external price history.

#### Scenario: Sufficient history

- **WHEN** a session has at least the configured minimum number of daily returns with non-zero variation
- **THEN** the system SHALL report a Sharpe ratio equal to the annualised mean-over-standard-deviation of those daily returns

#### Scenario: Contribution day excluded from the return series

- **WHEN** the Sharpe ratio is computed for a session that received a capital contribution on a day in its snapshot series
- **THEN** that day's return SHALL exclude the contributed amount, so adding capital does not register as a daily gain in the Sharpe computation

#### Scenario: Insufficient history

- **WHEN** a session has fewer than the configured minimum number of daily returns
- **THEN** the system SHALL report the Sharpe ratio as unavailable rather than a computed value

#### Scenario: No volatility

- **WHEN** a session's daily returns have zero standard deviation
- **THEN** the system SHALL report the Sharpe ratio as unavailable rather than dividing by zero
