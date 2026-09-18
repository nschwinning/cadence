## ADDED Requirements

### Requirement: Benchmark index catalog

The system SHALL offer a fixed catalog of selectable market benchmark indexes against which a paper-trading session can be compared. The catalog SHALL comprise: S&P 500, Dow Jones Industrial Average, NYSE Composite, Nasdaq Composite, Nasdaq-100, Russell 2000, S&P 100, and Wilshire 5000. Each catalog entry SHALL have a stable identifier used to reference it from a session, a human-readable display name, and a market-data symbol the system uses to fetch its prices. A client SHALL be able to read the catalog so it can present the available benchmarks for selection. A session SHALL reference a benchmark only by a catalog identifier; a value outside the catalog SHALL be rejected.

#### Scenario: Read the benchmark catalog

- **WHEN** a client requests the benchmark catalog
- **THEN** the system SHALL return the fixed set of benchmark indexes, each with its identifier and display name

#### Scenario: Only catalog benchmarks are accepted

- **WHEN** a request selects a benchmark identifier that is not in the catalog
- **THEN** the system SHALL reject the request rather than accept an unknown benchmark

### Requirement: Scheduled ingestion of benchmark index prices

The system SHALL, on a scheduled trigger, fetch and store the daily closing price of every benchmark index in the catalog into a benchmark price series keyed by benchmark identifier and date. The trigger SHALL be a cron-guarded endpoint protected by the shared cron-token secret, and SHALL reject a request with a missing or invalid token. Ingestion SHALL be idempotent per benchmark per date: re-running the trigger SHALL update the stored close for a date rather than create a duplicate. Ingestion SHALL store enough history for each benchmark that a session started in the past can be compared from its start date. A benchmark whose price data cannot be fetched SHALL be skipped without failing the ingestion of the other benchmarks.

#### Scenario: Daily ingestion stores index closes

- **WHEN** the benchmark-ingestion trigger runs with a valid cron token
- **THEN** the system SHALL fetch and store the daily closing prices for every catalog benchmark

#### Scenario: Ingestion is idempotent per benchmark and date

- **WHEN** the ingestion trigger runs more than once covering the same date for a benchmark
- **THEN** the system SHALL retain a single stored close per benchmark per date, reflecting the latest fetch, rather than creating duplicates

#### Scenario: One benchmark's failure does not abort ingestion

- **WHEN** one benchmark's price data cannot be fetched during ingestion
- **THEN** the system SHALL skip that benchmark and still ingest the others

#### Scenario: Invalid cron token is rejected

- **WHEN** the ingestion trigger is called without a valid cron token
- **THEN** the system SHALL reject the request and store no prices

### Requirement: Change a session's benchmark

The system SHALL let a client change the benchmark index a paper-trading session is compared against at any time, to any identifier in the benchmark catalog. Changing the benchmark SHALL affect subsequent comparisons for that session (its value-history benchmark values, KPI benchmark and excess return, and its line in the daily report) and SHALL NOT alter the session's recorded trades, positions, or value snapshots. A request to change the benchmark of an unknown session SHALL fail as not found, and a request naming a benchmark outside the catalog SHALL be rejected.

#### Scenario: Change the benchmark

- **WHEN** a client changes an existing session's benchmark to another catalog benchmark
- **THEN** the system SHALL persist the new benchmark for the session and subsequent comparisons SHALL use it

#### Scenario: Unknown session

- **WHEN** a client changes the benchmark of a session id that does not exist
- **THEN** the system SHALL respond with a not-found error

#### Scenario: Benchmark outside the catalog

- **WHEN** a client changes a session's benchmark to an identifier not in the catalog
- **THEN** the system SHALL reject the request and leave the session's benchmark unchanged

## MODIFIED Requirements

### Requirement: Build an AI portfolio and execute it as paper trades

The system SHALL accept a request to build an AI portfolio over the current asset universe and an amount of capital to allocate, with options for risk profile, whether the portfolio is enrolled in daily rebalancing, an **asset scope** selecting which asset types the portfolio may hold: stocks only, crypto only, or both, and an optional **benchmark index** (from the fixed benchmark catalog) the session's performance is compared against. The asset scope SHALL default to both (the whole supported universe) when not specified, the allocated capital SHALL default to a configured default amount, and the benchmark SHALL default to a configured default benchmark (S&P 500) when not specified. A benchmark selection outside the catalog SHALL be rejected. The request SHALL NOT accept a candidate ticker list or per-position allocation caps. The AI SHALL be given as candidates every asset in the universe **whose category is within the selected asset scope** (enriched with name, sector, category, and eligibility), MAY research and propose assets not currently in the universe (discovery is always enabled), and SHALL produce long-only target holdings whose allocations are fractions in [0, 1] that sum to approximately 1.0 (an allocation of ~0 excludes a holding). Newly discovered tickers SHALL be added to the universe on a best-effort basis, bounded by a configured maximum number of new assets per run, **and a discovered asset whose category falls outside the selected asset scope SHALL be rejected — not added and not traded**; if an in-scope add fails the ticker SHALL still be eligible for the portfolio. The selected asset scope SHALL be persisted with the session so that later automated rebalances honour the same scope. The selected benchmark SHALL be persisted with the session so the session can be compared against that benchmark over its lifetime. The request SHALL be processed in the background and SHALL return immediately with an event identifier for polling. Execution SHALL: ask the AI for target holdings and allocations, create a portfolio **with a generated distinct name** and a paper-trading session, size each position from the allocated capital and a current quote, submit the corresponding buy orders through the brokerage, and record each executed trade and a run summary. The generated portfolio name SHALL be human-friendly and SHALL be distinct from the names of existing portfolios, so that portfolios and their sessions can be told apart; the name MAY reflect the selected risk profile. The AI's research SHALL be cost-bounded per run by a configured maximum number of reasoning turns and a hard cap on the number of web searches.

#### Scenario: Queue a build

- **WHEN** a client requests an AI portfolio build while the asset universe is non-empty
- **THEN** the system SHALL create a build event, start background processing, and respond with the event id and a running status

#### Scenario: Empty universe rejected

- **WHEN** a client requests an AI portfolio build while the asset universe is empty
- **THEN** the system SHALL reject the request rather than starting a build

#### Scenario: Build executes

- **WHEN** the background build runs
- **THEN** the system SHALL create the portfolio and session, place the sized buy orders via the brokerage, record the executed trades and a run entry, and mark the build event succeeded (or partial if some orders could not be placed)

#### Scenario: Build assigns a distinct portfolio name

- **WHEN** the background build creates the portfolio
- **THEN** the system SHALL assign a generated, human-friendly name that differs from the names of existing portfolios

#### Scenario: Default capital and scope

- **WHEN** a client requests a build without specifying allocated capital or asset scope
- **THEN** the system SHALL use the configured default capital amount and an asset scope of both (stocks and crypto)

#### Scenario: Default benchmark

- **WHEN** a client requests a build without specifying a benchmark
- **THEN** the system SHALL persist the configured default benchmark (S&P 500) as the session's benchmark

#### Scenario: Build persists a chosen benchmark

- **WHEN** a client requests a build selecting a benchmark from the catalog
- **THEN** the system SHALL persist that benchmark with the created session

#### Scenario: Scope restricts the candidate universe

- **WHEN** a build requests an asset scope of stocks only (or crypto only)
- **THEN** the AI SHALL be given only universe assets whose category matches the scope, and the resulting portfolio SHALL contain only assets of the selected type

#### Scenario: AI discovers a new asset

- **WHEN** the AI proposes a holding whose ticker is not in the current universe and whose category is within the selected asset scope
- **THEN** the system SHALL attempt to add that asset to the universe (up to the configured per-run limit) and SHALL still include the ticker in the portfolio and its trades even if the add fails

#### Scenario: AI discovers an out-of-scope asset

- **WHEN** the AI proposes a holding whose category falls outside the selected asset scope
- **THEN** the system SHALL reject that asset — neither adding it to the universe nor trading it — while continuing the rest of the build

#### Scenario: Position too small to trade

- **WHEN** an allocation buys less than one whole share at the current quote
- **THEN** the system SHALL skip that position without failing the whole build and SHALL record it as not executed

### Requirement: Read paper-trading session data

The system SHALL let a client list paper-trading sessions and read a session's trades, runs, positions, its AI-portfolio events, and its daily portfolio-value snapshots. A session returned to a client SHALL include the name of the portfolio it trades so the client can identify the session by portfolio; when the portfolio cannot be resolved the name SHALL be absent (null) rather than causing an error. A session returned to a client SHALL include the benchmark it is compared against. An AI-portfolio event returned to a client SHALL include the AI's reasoning output and its persisted research transcript. A trade or closed position returned to a client SHALL include the reference to the AI-portfolio event that produced it, when present. A session's value history SHALL be returned ordered oldest snapshot first, and each snapshot in the returned history SHALL carry the value of a buy-and-hold of the session's allocated capital in the session's benchmark as of that snapshot's date, derived from the stored benchmark price series and rebased so the benchmark equals the allocated capital on the session's first snapshot date. When the benchmark has no stored price on or before a snapshot's date, that snapshot's benchmark value SHALL be absent (null) rather than causing an error.

#### Scenario: Inspect a session

- **WHEN** a client requests a session's trades, runs, positions, or events
- **THEN** the system SHALL return the recorded data for that session

#### Scenario: Session identifies its portfolio

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include the name of the portfolio it trades

#### Scenario: Session reports its benchmark

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include the benchmark it is compared against

#### Scenario: Event includes reasoning and research

- **WHEN** a client reads an AI-portfolio event
- **THEN** the returned event SHALL include the AI reasoning output and the persisted research transcript

#### Scenario: Read session value history

- **WHEN** a client requests a session's value history
- **THEN** the system SHALL return the session's daily value snapshots ordered oldest first, each with its date, total value, cash value, positions value, day's profit and loss, and the rebased benchmark value as of that date

#### Scenario: Benchmark price missing for a date

- **WHEN** a client requests a session's value history and the benchmark has no stored price on or before a snapshot's date
- **THEN** the system SHALL return that snapshot with the benchmark value absent rather than failing the request

### Requirement: Live session performance KPIs

The system SHALL expose, on demand for a given paper-trading session, a summary of the session's live performance comprising: the current portfolio value (net asset value: cash plus open positions valued at current market quotes, net of cumulative transaction fees), cumulative realised profit/loss, live unrealised profit/loss on open positions, cumulative transaction fees paid, total return relative to the allocated capital (as both an absolute money amount and a fraction), a risk-adjusted Sharpe ratio, the benchmark it is compared against, the benchmark's total return over the same period as a fraction, and the session's excess return over the benchmark as a fraction. The benchmark return SHALL be the fractional return of a buy-and-hold of the benchmark from the session's start to the latest available benchmark price, derived from the stored benchmark price series, and the excess return SHALL be the session's total-return fraction minus the benchmark's return fraction. When the benchmark has insufficient stored prices to compute a return the benchmark return and excess return SHALL be reported as unavailable (no value) rather than failing the request. Requesting the summary SHALL value the session's open positions against current quotes at request time (marking to market on load) rather than returning a stale stored valuation. A request for an unknown session SHALL fail as not found.

#### Scenario: Summary for a session with open positions

- **WHEN** a client requests the KPI summary for an existing session
- **THEN** the system SHALL mark the session's open positions to market and return the current portfolio value (net of transaction fees), realised P&L, unrealised P&L, cumulative transaction fees, total return relative to allocated capital, the Sharpe ratio (or an unavailable Sharpe when history is insufficient), the benchmark return, and the excess return over the benchmark

#### Scenario: Unknown session

- **WHEN** a client requests the KPI summary for a session id that does not exist
- **THEN** the system SHALL respond with a not-found error and no summary

#### Scenario: Total return relative to allocated capital

- **WHEN** the KPI summary is computed
- **THEN** the total return SHALL be the current portfolio value measured against the session's allocated capital, provided both as an absolute money amount (current value minus allocated capital) and as a fraction of allocated capital

#### Scenario: Benchmark and excess return reported

- **WHEN** the KPI summary is computed and the benchmark has sufficient stored prices
- **THEN** the summary SHALL include the benchmark's fractional return over the session's period and the session's excess return (the session's total-return fraction minus the benchmark's return fraction)

#### Scenario: Benchmark unavailable

- **WHEN** the KPI summary is computed but the benchmark has insufficient stored prices
- **THEN** the summary SHALL report the benchmark return and excess return as unavailable rather than failing the request

#### Scenario: Cumulative transaction fees reported

- **WHEN** a client requests the KPI summary for a session that has executed trades
- **THEN** the summary SHALL include the session's cumulative transaction fees as a non-negative money amount

### Requirement: Snapshot session portfolio value at end of day

The system SHALL, on a scheduled end-of-day trigger, record one portfolio-value
snapshot per active AI-managed session (a session whose strategy is AI-managed and
whose status is active) and send a daily profit-and-loss report. The trigger SHALL
be a cron-guarded endpoint protected by the shared cron-token secret, and SHALL
reject a request with a missing or invalid token. Recording SHALL be idempotent per
session per day: re-running the trigger on the same calendar day SHALL update that
day's snapshot rather than create a duplicate.

Each snapshot SHALL record the session's total value, its cash value, the market
value of its held positions, the day's profit and loss (absolute and percent), and a
per-position breakdown (per held ticker: quantity, price, market value, unrealized
profit and loss, and return). A session's total value SHALL be computed by marking its
open positions — taken from the session's position ledger — to market and combining
them with the session's allocated capital and realized profit and loss. The day's
profit and loss SHALL be measured against the
session's most recent prior snapshot, or against its allocated capital when no prior
snapshot exists. A session holding no positions SHALL record an all-cash snapshot.

The report SHALL contain, for each session snapshotted, a line with the session's
total value and the day's profit and loss (absolute and percent), the session's
benchmark and the session's return versus that benchmark (the benchmark's return over
the session's period and the session's excess return), plus the single
best-performing and single worst-performing individual holding ranked by return
across all snapshotted sessions. When a session's benchmark comparison is
unavailable, its line SHALL still be reported without the benchmark figures. A failure
to deliver the report SHALL NOT fail the snapshot job.

#### Scenario: Daily snapshot recorded for active AI sessions

- **WHEN** the end-of-day snapshot trigger runs with a valid cron token
- **THEN** the system SHALL record a value snapshot for each active AI-managed
  session and SHALL NOT record snapshots for paused, stopped, or non-AI sessions

#### Scenario: Snapshot is idempotent per day

- **WHEN** the snapshot trigger runs twice on the same calendar day for a session
- **THEN** the system SHALL retain a single snapshot for that session and day,
  reflecting the latest run, rather than creating a duplicate

#### Scenario: Daily P&L baseline

- **WHEN** a snapshot is recorded for a session that has a prior snapshot
- **THEN** the day's profit and loss SHALL be the change in total value since the
  prior snapshot; **AND WHEN** the session has no prior snapshot, the day's profit
  and loss SHALL be measured against the session's allocated capital

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
