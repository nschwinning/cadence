## ADDED Requirements

### Requirement: Automatic stop-loss protection for opted-in sessions

The system SHALL provide a scheduled entry point that enforces automatic hard
stop-losses across every active AI-managed session that has the stop-loss enabled,
independently of the daily rebalance and intended to run more frequently than it. The
entry point SHALL be protected by the shared cron-token secret and SHALL reject a
request with a missing or invalid token.

For each such session, the system SHALL value each of the session's open positions
(taken from the session's position ledger) against its current market price and SHALL
**fully sell** any position whose current price is at or below its **stop-loss
trigger** — defined as the position's weighted-average cost reduced by the session's
frozen stop-loss threshold percentage (`avg_cost × (1 − stop_loss_pct)`). A position
whose current price is above its trigger SHALL be left unchanged. A session whose
stop-loss is disabled (including a session with no persisted stop-loss setting) SHALL
be skipped entirely. Equity positions SHALL be sold only while the equities market is
open; crypto positions MAY be sold at any time. When a position's current price cannot
be obtained, that position SHALL be left unchanged and the scan SHALL continue.

When the system stops out a position it SHALL record the sale through the same
execution path as any other exit: a trade marked with a **stop-loss signal type** and
**not attributed to any AI-portfolio event**, a run entry recording the stop-loss
execution, and a closed position with realized profit and loss; the per-trade
transaction cost SHALL be charged for the sale. The system SHALL send a best-effort
push notification for each stop-out; a failure to send the notification SHALL be
logged and SHALL NOT change or roll back the recorded sale, run, or closed position.

When a position is stopped out, the system SHALL record a per-session **quarantine**
for that ticker with an expiry a configured number of trading days in the future, so
that the automated rebalance does not immediately re-enter the position (see the
daily-rebalancing candidate-assembly requirement). A failure to process one session
SHALL NOT prevent the remaining sessions from being processed.

#### Scenario: Position below its trigger is stopped out

- **WHEN** the stop-loss scan runs and an opted-in session holds a position whose
  current price is at or below its weighted-average cost reduced by the session's
  stop-loss threshold
- **THEN** the system SHALL fully sell that position, record the sale, and realize its
  profit and loss

#### Scenario: Position above its trigger is held

- **WHEN** the stop-loss scan runs and a held position's current price is above its
  stop-loss trigger
- **THEN** the system SHALL leave that position unchanged

#### Scenario: Stop-loss disabled session is skipped

- **WHEN** the stop-loss scan runs and a session has the stop-loss disabled (or no
  persisted stop-loss setting)
- **THEN** the system SHALL not sell any of that session's positions on account of a
  stop-loss

#### Scenario: Equity stop-out deferred while the market is closed

- **WHEN** an equity position breaches its stop-loss trigger while the equities market
  is closed
- **THEN** the system SHALL not place the equity sell during that scan, while still
  stopping out any breached crypto positions

#### Scenario: Stop-out recorded as a non-AI exit

- **WHEN** the system stops out a position
- **THEN** the recorded trade SHALL be marked as a stop-loss sale with no AI-portfolio
  event reference, a run entry SHALL record the stop-loss execution, a closed position
  SHALL record the realized profit and loss, and the per-trade transaction cost SHALL
  be charged

#### Scenario: Stop-out quarantines the ticker

- **WHEN** the system stops out a position for a session
- **THEN** the system SHALL record a quarantine for that ticker on that session with an
  expiry a configured number of trading days ahead

#### Scenario: Stop-out sends a best-effort notification

- **WHEN** the system stops out one or more positions
- **THEN** the system SHALL send a push notification for the stop-out, and a failure to
  send it SHALL NOT roll back the recorded sale

#### Scenario: One session's failure does not stop the rest

- **WHEN** processing one session during a stop-loss scan fails
- **THEN** the system SHALL continue processing the remaining sessions

#### Scenario: Invalid cron token is rejected

- **WHEN** the stop-loss scan entry point is called without a valid cron token
- **THEN** the system SHALL reject the request and SHALL NOT sell any position

## MODIFIED Requirements

### Requirement: Build an AI portfolio and execute it as paper trades

The system SHALL accept a request to build an AI portfolio over the current asset universe and an amount of capital to allocate, with options for risk profile, whether the portfolio is enrolled in daily rebalancing, an **asset scope** selecting which asset types the portfolio may hold: stocks only, crypto only, or both, whether the portfolio **uses the technical-indicator trend strategy** (an opt-in that defaults to off when not specified), whether the portfolio **enables an automatic hard stop-loss** (an opt-in that defaults to off when not specified) together with a **stop-loss threshold percentage** (defaulting to a configured default when the stop-loss is enabled without an explicit threshold), and an optional **benchmark index** (from the fixed benchmark catalog) the session's performance is compared against. The asset scope SHALL default to both (the whole supported universe) when not specified, the allocated capital SHALL default to a configured default amount, and the benchmark SHALL default to a configured default benchmark (S&P 500) when not specified. A benchmark selection outside the catalog SHALL be rejected. The request SHALL NOT accept a candidate ticker list or per-position allocation caps. The AI SHALL be given as candidates every asset in the universe **whose category is within the selected asset scope** (enriched with name, sector, category, and eligibility). **When the session opts into the technical-indicator trend strategy**, the candidate set SHALL additionally be restricted to assets whose latest stored technical-indicator snapshot passes the deterministic uptrend trend gate — a candidate whose gate does not pass, or that has no stored snapshot, SHALL be dropped and SHALL NOT be presented to the AI, so that a portfolio is only ever initialised with assets in a confirmed uptrend — and the surviving candidates SHALL be annotated with their trend indicators. **When the session does not opt in, no trend gate SHALL be applied and every in-scope candidate SHALL be presented to the AI without indicator annotations.** The AI MAY research and propose assets not currently in the universe (discovery is always enabled), and SHALL produce long-only target holdings whose allocations are fractions in [0, 1] that sum to approximately 1.0 (an allocation of ~0 excludes a holding). Newly discovered tickers SHALL be added to the universe on a best-effort basis, bounded by a configured maximum number of new assets per run, **and a discovered asset whose category falls outside the selected asset scope SHALL be rejected — not added and not traded**, and — **only when the session opted into the trend strategy** — a discovered asset that does not pass the trend gate SHALL likewise be excluded from the candidate set; if an in-scope add fails the ticker SHALL still be eligible for the portfolio. The selected asset scope SHALL be persisted with the session so that later automated rebalances honour the same scope. The selected technical-indicator opt-in SHALL be persisted (frozen) with the session so that later automated rebalances apply the same choice; a session with no persisted opt-in (for example one built before this option existed) SHALL be treated as opted out. The selected stop-loss opt-in and, when enabled, its threshold percentage SHALL be persisted (frozen) with the session so the automatic stop-loss applies for the session's lifetime; a session with no persisted stop-loss setting (for example one built before this option existed) SHALL be treated as having the stop-loss disabled. The selected benchmark SHALL be persisted with the session so the session can be compared against that benchmark over its lifetime. The request SHALL be processed in the background and SHALL return immediately with an event identifier for polling. Execution SHALL: ask the AI for target holdings and allocations, create a portfolio **with a generated distinct name** and a paper-trading session, size each position from the allocated capital and a current quote, submit the corresponding buy orders through the brokerage, and record each executed trade and a run summary. The generated portfolio name SHALL be human-friendly and SHALL be distinct from the names of existing portfolios, so that portfolios and their sessions can be told apart; the name MAY reflect the selected risk profile. The AI's research SHALL be cost-bounded per run by a configured maximum number of reasoning turns and a hard cap on the number of web searches.

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

#### Scenario: Stop-loss disabled by default

- **WHEN** a client requests a build without enabling the stop-loss
- **THEN** the system SHALL persist the session with the automatic stop-loss disabled

#### Scenario: Build persists the stop-loss setting

- **WHEN** a client requests a build enabling the stop-loss, optionally with a threshold percentage
- **THEN** the system SHALL persist the stop-loss as enabled on the created session, using the given threshold or the configured default when none is given

#### Scenario: Scope restricts the candidate universe

- **WHEN** a build requests an asset scope of stocks only (or crypto only)
- **THEN** the AI SHALL be given only universe assets whose category matches the scope, and the resulting portfolio SHALL contain only assets of the selected type

#### Scenario: Build opts out of the trend strategy by default

- **WHEN** a client requests a build without specifying the technical-indicator opt-in
- **THEN** the system SHALL persist the session as opted out, SHALL NOT apply the trend gate, and SHALL present every in-scope candidate to the AI without indicator annotations

#### Scenario: Trend gate restricts the candidate universe

- **WHEN** a build that opted into the technical-indicator trend strategy assembles the candidate universe
- **THEN** the system SHALL present to the AI only in-scope candidates whose latest indicator snapshot passes the uptrend gate (dropping those that fail or have no snapshot), so the initial portfolio only enters trend-confirmed assets

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

The system SHALL let a client list paper-trading sessions and read a session's trades, runs, positions, its AI-portfolio events, and its daily portfolio-value snapshots. A session returned to a client SHALL include the name of the portfolio it trades so the client can identify the session by portfolio; when the portfolio cannot be resolved the name SHALL be absent (null) rather than causing an error. A session returned to a client SHALL include the benchmark it is compared against. A session returned to a client SHALL include its stop-loss configuration: whether the automatic stop-loss is enabled and, when enabled, its threshold percentage. An AI-portfolio event returned to a client SHALL include the AI's reasoning output and its persisted research transcript. A trade or closed position returned to a client SHALL include the reference to the AI-portfolio event that produced it, when present. A session's value history SHALL be returned ordered oldest snapshot first, and each snapshot in the returned history SHALL carry the value of a buy-and-hold of the session's allocated capital in the session's benchmark as of that snapshot's date, derived from the stored benchmark price series and rebased so the benchmark equals the allocated capital on the session's first snapshot date. When the benchmark has no stored price on or before a snapshot's date, that snapshot's benchmark value SHALL be absent (null) rather than causing an error.

#### Scenario: Inspect a session

- **WHEN** a client requests a session's trades, runs, positions, or events
- **THEN** the system SHALL return the recorded data for that session

#### Scenario: Session identifies its portfolio

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include the name of the portfolio it trades

#### Scenario: Session reports its benchmark

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include the benchmark it is compared against

#### Scenario: Session reports its stop-loss configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its automatic stop-loss is enabled and, when enabled, its threshold percentage

#### Scenario: Event includes reasoning and research

- **WHEN** a client reads an AI-portfolio event
- **THEN** the returned event SHALL include the AI reasoning output and the persisted research transcript

#### Scenario: Read session value history

- **WHEN** a client requests a session's value history
- **THEN** the system SHALL return the session's daily value snapshots ordered oldest first, each with its date, total value, cash value, positions value, day's profit and loss, and the rebased benchmark value as of that date

#### Scenario: Benchmark price missing for a date

- **WHEN** a client requests a session's value history and the benchmark has no stored price on or before a snapshot's date
- **THEN** the system SHALL return that snapshot with the benchmark value absent rather than failing the request
