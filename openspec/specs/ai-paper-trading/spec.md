# ai-paper-trading Specification

## Purpose
Lets an AI assemble a portfolio and execute it as simulated (paper) trades on a brokerage, recording the resulting session, trades, and an auditable trail of AI decisions, so a user can watch an AI-managed strategy run against real market prices without risking capital.

## Requirements

### Requirement: Brokerage abstraction with paper/live and offline modes

The system SHALL access the brokerage through a single abstraction exposing account information, positions, quotes, order submission, order status, and a market-open check. Whether it targets the paper or live brokerage endpoint SHALL be determined by configuration, defaulting to paper. The system SHALL support an offline mode (selectable by configuration) that simulates the brokerage without any network calls, for local development and tests.

#### Scenario: Paper mode by default

- **WHEN** no live mode is configured
- **THEN** the system SHALL direct all brokerage calls to the paper trading endpoint

#### Scenario: Offline mode

- **WHEN** offline brokerage mode is enabled
- **THEN** the system SHALL satisfy account, position, quote, and order operations without external network calls

#### Scenario: Missing credentials

- **WHEN** live/paper mode is active but brokerage credentials are absent
- **THEN** the system SHALL fail the operation with a clear error rather than sending an unauthenticated request

### Requirement: Build an AI portfolio and execute it as paper trades

The system SHALL accept a request to build an AI portfolio over the current asset universe and an amount of capital to allocate, with options for risk profile, whether the portfolio is enrolled in daily rebalancing, an **asset scope** selecting which asset types the portfolio may hold: stocks only, crypto only, or both, whether the portfolio **uses the technical-indicator trend strategy** (an opt-in that defaults to off when not specified), whether the portfolio **enables an automatic hard stop-loss** (an opt-in that defaults to off when not specified) together with a **stop-loss threshold percentage** (defaulting to a configured default when the stop-loss is enabled without an explicit threshold), whether the portfolio **enables portfolio risk guardrails** (an opt-in that defaults to off when not specified) together with the guardrail parameters — a **maximum percentage per asset**, a **maximum percentage per asset class**, a **minimum number of positions**, and a **maximum invested percentage** (cash buffer) — each defaulting to a configured default when the guardrails are enabled without an explicit value, and an optional **benchmark index** (from the fixed benchmark catalog) the session's performance is compared against. The asset scope SHALL default to both (the whole supported universe) when not specified, the allocated capital SHALL default to a configured default amount, and the benchmark SHALL default to a configured default benchmark (S&P 500) when not specified. A benchmark selection outside the catalog SHALL be rejected. The request SHALL NOT accept a candidate ticker list. The request MAY carry the guardrail parameters described above; it SHALL NOT accept any other per-position allocation cap. The AI SHALL be given as candidates every asset in the universe **whose category is within the selected asset scope** (enriched with name, sector, category, and eligibility). **When the session opts into the technical-indicator trend strategy**, the candidate set SHALL additionally be restricted to assets whose latest stored technical-indicator snapshot passes the deterministic uptrend trend gate — a candidate whose gate does not pass, or that has no stored snapshot, SHALL be dropped and SHALL NOT be presented to the AI, so that a portfolio is only ever initialised with assets in a confirmed uptrend — and the surviving candidates SHALL be annotated with their trend indicators. **When the session does not opt in, no trend gate SHALL be applied and every in-scope candidate SHALL be presented to the AI without indicator annotations.** The AI MAY research and propose assets not currently in the universe (discovery is always enabled), and SHALL produce long-only target holdings whose allocations are fractions in [0, 1] that sum to approximately 1.0 (an allocation of ~0 excludes a holding). Newly discovered tickers SHALL be added to the universe on a best-effort basis, bounded by a configured maximum number of new assets per run, **and a discovered asset whose category falls outside the selected asset scope SHALL be rejected — not added and not traded**, and — **only when the session opted into the trend strategy** — a discovered asset that does not pass the trend gate SHALL likewise be excluded from the candidate set; if an in-scope add fails the ticker SHALL still be eligible for the portfolio. **When the session opted into the risk guardrails, the AI SHALL additionally be told the guardrail caps (maximum per asset, maximum per asset class, minimum number of positions, and maximum invested percentage) so it can plan within them.** The selected asset scope SHALL be persisted with the session so that later automated rebalances honour the same scope. The selected technical-indicator opt-in SHALL be persisted (frozen) with the session so that later automated rebalances apply the same choice; a session with no persisted opt-in (for example one built before this option existed) SHALL be treated as opted out. The selected stop-loss opt-in and, when enabled, its threshold percentage SHALL be persisted (frozen) with the session so the automatic stop-loss applies for the session's lifetime; a session with no persisted stop-loss setting (for example one built before this option existed) SHALL be treated as having the stop-loss disabled. The selected risk-guardrail opt-in and, when enabled, its parameters (maximum per asset, maximum per asset class, minimum number of positions, maximum invested percentage) SHALL be persisted (frozen) with the session so the same guardrails apply for the session's lifetime; a session with no persisted guardrail setting (for example one built before this option existed) SHALL be treated as having the guardrails disabled. The selected benchmark SHALL be persisted with the session so the session can be compared against that benchmark over its lifetime. The request SHALL be processed in the background and SHALL return immediately with an event identifier for polling. Execution SHALL: ask the AI for target holdings and allocations, create a portfolio **with a generated distinct name** and a paper-trading session, **when the guardrails are enabled deterministically enforce them on the target-weight vector before sizing** so that no single holding exceeds the maximum-per-asset cap, no asset class exceeds the maximum-per-class cap, and the total invested fraction does not exceed the maximum invested percentage (the remainder held as cash) — excess weight removed by a per-asset or per-class cap SHALL be redistributed proportionally to the holdings still below their caps, and when the caps cannot absorb the full capital the shortfall SHALL remain as cash — size each position from the allocated capital and a current quote, submit the corresponding buy orders through the brokerage, and record each executed trade and a run summary. The deterministic guardrail enforcement is the guarantee; the caps given to the AI are advisory only. The minimum-number-of-positions guardrail SHALL NOT be enforced by fabricating holdings the AI did not pick: it is applied as the AI instruction above plus the diversification floor implied by the maximum-per-asset cap, and when the AI returns fewer holdings than the configured minimum the shortfall SHALL be recorded as a guardrail observation on the run rather than causing the build to fail. The generated portfolio name SHALL be human-friendly and SHALL be distinct from the names of existing portfolios, so that portfolios and their sessions can be told apart; the name MAY reflect the selected risk profile. The AI's research SHALL be cost-bounded per run by a configured maximum number of reasoning turns and a hard cap on the number of web searches.

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

#### Scenario: Guardrails disabled by default

- **WHEN** a client requests a build without enabling the risk guardrails
- **THEN** the system SHALL persist the session with the risk guardrails disabled and SHALL apply no allocation caps during the build

#### Scenario: Build persists the guardrail settings

- **WHEN** a client requests a build enabling the risk guardrails, optionally with parameters
- **THEN** the system SHALL persist the guardrails as enabled on the created session, using the given maximum-per-asset, maximum-per-class, minimum-positions, and maximum-invested values or the configured defaults when any is not given

#### Scenario: Build clamps an over-cap holding

- **WHEN** a build with guardrails enabled receives AI target allocations in which a single holding exceeds the maximum-per-asset cap
- **THEN** the system SHALL reduce that holding to the cap and redistribute the excess weight to the remaining holdings still below their caps before sizing the positions

#### Scenario: Build caps an over-concentrated asset class

- **WHEN** a build with guardrails enabled receives AI target allocations whose combined weight in one asset class exceeds the maximum-per-class cap
- **THEN** the system SHALL reduce that class's combined weight to the cap and redistribute the excess to holdings in other classes still below their caps before sizing

#### Scenario: Build holds back a cash buffer

- **WHEN** a build with guardrails enabled has a maximum invested percentage below 100%
- **THEN** the system SHALL scale the target weights so the total invested does not exceed the maximum invested percentage and SHALL leave the remainder as cash

#### Scenario: Build records a minimum-positions shortfall without fabricating holdings

- **WHEN** a build with guardrails enabled receives AI target allocations containing fewer holdings than the configured minimum number of positions
- **THEN** the system SHALL NOT invent additional holdings and SHALL record the shortfall as a guardrail observation on the run while completing the build with the AI's holdings (after clamping)

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

### Requirement: Poll AI portfolio build status

The system SHALL let a client fetch the status of a build event by its identifier, exposing the run status, the resulting session and portfolio identifiers, the AI's structured output, the actions taken, any error, and a duration.

#### Scenario: Poll a build event

- **WHEN** a client polls a build event id
- **THEN** the system SHALL return the current status and, once finished, the session id, portfolio id, and the actions taken

### Requirement: Record sessions, trades, runs, and closed positions

The system SHALL persist, per paper-trading session, the executed trades (ticker, side, quantity, price, notional, signal type, order identity and status), a run entry per execution (counts and a trigger and status), the session's open positions in a ledger (per held ticker: quantity, weighted-average cost, and opened date), and closed positions with realized profit and loss when positions are exited. Every executed fill SHALL update the open-position ledger (a buy opens or increases an entry and re-computes its weighted-average cost; a sell reduces or removes it), and realized profit and loss SHALL be derived from the ledger entry's average cost and opened date. Each AI build or rebalance SHALL be recorded as an AI-portfolio event capturing the AI's output (its reasoning) and the actions taken, and SHALL also persist the run's research transcript: the web searches performed during the run and, for each, the query and the results the agent received (or a note when a search was not performed, e.g. the per-run search budget was exhausted). Each trade, each closed position, and each run produced by an AI build or rebalance SHALL record a reference to the AI-portfolio event that produced it; trades, closed positions, and runs not produced by an AI build or rebalance — such as automatic stop-loss runs or scheduled/manual scanner runs — SHALL leave this reference empty.

#### Scenario: Trades and run recorded on execution

- **WHEN** a build or rebalance places orders
- **THEN** the system SHALL record a trade per executed order, a run entry summarizing the execution, updated open-position ledger entries, and (for exits) closed positions with realized P&L

#### Scenario: Trades and closed positions reference their run

- **WHEN** an AI build or rebalance records a trade or a closed position
- **THEN** the recorded trade or closed position SHALL reference the AI-portfolio event that produced it

#### Scenario: Runs reference their producing AI event

- **WHEN** an AI build or rebalance records a run entry
- **THEN** the recorded run SHALL reference the AI-portfolio event that produced it

#### Scenario: Non-AI runs leave the event reference empty

- **WHEN** a run is recorded that was not produced by an AI build or rebalance — for example an automatic stop-loss run or a scheduled/manual scanner run
- **THEN** the recorded run SHALL leave the AI-portfolio event reference empty

#### Scenario: Research transcript persisted

- **WHEN** an AI build or rebalance reaches the agent and the agent performs web searches
- **THEN** the recorded AI-portfolio event SHALL persist each search's query and the results the agent received

#### Scenario: Research captured despite a mid-run failure

- **WHEN** an AI run fails after the agent has already performed one or more web searches
- **THEN** the recorded (failed) AI-portfolio event SHALL still persist the research captured before the failure

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

### Requirement: Change a session's asset scope

The system SHALL let a client change a paper-trading session's asset scope at any time to one of the supported scopes: stocks only, crypto only, or both. The new scope SHALL be persisted on the session so that all subsequent behavior keyed off scope — the assets an AI build or rebalance may target and discover, weekend crypto-rebalance selection, and weekend value-snapshot gating — honors the new scope. A request naming a scope outside the supported set SHALL be rejected and leave the session's scope unchanged. A request to change the scope of an unknown session SHALL fail as not found. Changing a session to the scope it already has SHALL be a successful no-op that neither liquidates holdings nor otherwise alters the session.

When the new scope EXCLUDES the asset class of one or more currently-held positions (a narrowing), the system SHALL immediately liquidate those now-out-of-scope positions as part of the scope change: it SHALL sell each out-of-scope position through the broker, record the resulting trades including the standard per-trade transaction cost (accumulated into the session's total fees like any other trade), close those positions in the session's ledger, and refresh the session's recorded value so the valuation reflects the sales. Positions whose asset class remains within the new scope SHALL NOT be sold. Widening the scope, or any scope change that excludes nothing currently held, SHALL liquidate nothing. When the scope change requires broker access but the broker is unavailable or unreachable, the system SHALL fail the request rather than record a scope change without performing the required liquidation.

#### Scenario: Change the scope

- **WHEN** a client changes an existing session's scope to another supported scope
- **THEN** the system SHALL persist the new scope and subsequent builds, rebalances, weekend crypto selection, and weekend snapshot gating SHALL use it

#### Scenario: Narrowing liquidates out-of-scope holdings

- **WHEN** a client narrows a session's scope so that a currently-held position's asset class is no longer in scope
- **THEN** the system SHALL sell that position through the broker, record the sale with the per-trade transaction cost accumulated into the session's total fees, close it in the ledger, and refresh the session's recorded value

#### Scenario: Widening liquidates nothing

- **WHEN** a client widens a session's scope, or changes it in a way that excludes no currently-held position
- **THEN** the system SHALL persist the new scope and SHALL NOT sell any position

#### Scenario: Unchanged scope is a no-op

- **WHEN** a client changes a session's scope to the scope it already has
- **THEN** the system SHALL succeed without liquidating any holdings or otherwise altering the session

#### Scenario: Unknown session

- **WHEN** a client changes the scope of a session id that does not exist
- **THEN** the system SHALL respond with a not-found error

#### Scenario: Scope outside the supported set

- **WHEN** a client changes a session's scope to a value that is not one of the supported scopes
- **THEN** the system SHALL reject the request and leave the session's scope unchanged

#### Scenario: Broker unavailable during a narrowing

- **WHEN** a narrowing scope change needs to liquidate out-of-scope holdings but the broker is unavailable or unreachable
- **THEN** the system SHALL fail the request rather than persist a scope change without performing the required liquidation

### Requirement: Trade both equities and crypto assets

The system SHALL determine each asset's class (equity or crypto) from its stored
asset record and route brokerage calls accordingly. For crypto it SHALL translate
symbols between the universe's canonical format (e.g. `BTC-USD`) and the brokerage
format (e.g. `BTC/USD`) at the brokerage boundary, submit orders with a
crypto-compatible time-in-force and fractional quantities, and read quotes from the
brokerage's crypto market-data endpoints. Positions returned by the brokerage SHALL
be reconciled back to canonical universe tickers. Equity routing SHALL be unchanged.

#### Scenario: Crypto order routing

- **WHEN** the executor places an order for an asset classified as crypto
- **THEN** the system SHALL send the brokerage-format crypto symbol with a
  crypto-compatible time-in-force and a fractional quantity, not an equities-style
  whole-share day order

#### Scenario: Crypto quote routing

- **WHEN** the executor requests a quote for a crypto asset
- **THEN** the system SHALL obtain the price from the brokerage's crypto market-data
  endpoint rather than the equities endpoint

#### Scenario: Position reconciliation

- **WHEN** the brokerage reports a crypto position in its own symbol format
- **THEN** the system SHALL map it to the canonical universe ticker so it matches
  the portfolio's holdings during rebalance

### Requirement: Fractional sizing for crypto

The system SHALL size crypto positions as fractional units of the asset, skipping a
position only when its value falls below the brokerage's minimum tradable notional.
Equity positions SHALL continue to be sized in whole shares, skipping allocations
smaller than one share.

#### Scenario: Fractional crypto position

- **WHEN** a crypto allocation buys less than one whole unit at the current price
- **THEN** the system SHALL place a fractional-unit order rather than skipping it

#### Scenario: Below minimum notional

- **WHEN** a crypto allocation's value is below the brokerage minimum notional
- **THEN** the system SHALL skip that position without failing the run and record it
  as not executed

### Requirement: Rebalance crypto around the clock

Because crypto trades 24/7, the daily rebalance SHALL execute crypto trades even
when the equities market is closed. When the equities market is closed, the system
SHALL still rebalance crypto holdings and targets and SHALL skip only the equity
orders. The system SHALL record the run as skipped (no orders) only when nothing is
tradable — that is, the equities market is closed and neither the current positions
nor the targets include any crypto.

#### Scenario: Crypto rebalances while equities market is closed

- **WHEN** a daily rebalance runs while the equities market is closed and the
  session holds or targets crypto
- **THEN** the system SHALL trade the crypto toward its targets and skip equity
  orders, recording the run as executed rather than skipped

#### Scenario: Nothing tradable while closed

- **WHEN** a daily rebalance runs while the equities market is closed and neither
  the positions nor the targets include any crypto
- **THEN** the system SHALL record a skipped run and mark the rebalance event
  skipped

### Requirement: Weekend crypto rebalance selects sessions by configured crypto scope

The scheduled crypto-only (weekend) rebalance SHALL select the sessions it rebalances by each session's **configured** asset scope rather than its current holdings. It SHALL rebalance only active daily-rebalancing AI-managed sessions whose configured asset scope includes crypto (scope is crypto or both). A session configured stocks-only SHALL be excluded from the crypto-only rebalance and reported as skipped for not being crypto-scoped, even if it currently holds or targets a crypto asset. A session with no persisted scope (for example one built before an explicit scope existed) SHALL be treated as the default scope (both) and is therefore included.

#### Scenario: Stocks-only session excluded even when holding crypto

- **WHEN** the crypto-only rebalance runs and an active daily-rebalancing session is configured stocks-only but currently holds or targets a crypto asset
- **THEN** the system SHALL exclude that session from the crypto-only rebalance, report it as skipped for not being crypto-scoped, and SHALL NOT place any crypto order for it

#### Scenario: Crypto and both scopes are rebalanced

- **WHEN** the crypto-only rebalance runs and an active daily-rebalancing session's configured scope is crypto or both
- **THEN** the system SHALL include that session in the crypto-only rebalance

### Requirement: Skip a rebalance run that can only buy with no deployable cash

During any rebalance (full or crypto-only), after the run has planned its sell and buy intents and **before it submits any order**, the system SHALL skip the run when the plan contains **no sell intents** AND the session has **no deployable unallocated cash** to fund the planned buys. Deployable unallocated cash SHALL be the session's free cash in excess of the reserved cash buffer — the cash available to fund new buys once the buffer is set aside — and is "none" when it is insufficient to fund any planned buy. When the run is skipped this way the system SHALL submit no orders, record the run as a skipped/no-op run, and send the informational skip notification described in "Notify when a selected session's rebalance is skipped" rather than the trade-success notification. A run whose plan includes at least one sell SHALL proceed (it reallocates), and a buy-only run that has deployable unallocated cash SHALL proceed (it deploys the cash). As a consequence, the first rebalance immediately after a build — when the allocated capital is already deployed and only the reserved cash buffer remains — SHALL be skipped.

#### Scenario: Buy-only plan with no deployable cash is skipped

- **WHEN** a rebalance plans only buy intents (no sells) and the session has no unallocated cash beyond the reserved cash buffer to fund them
- **THEN** the system SHALL submit no orders, record the run as skipped, and send the informational skip notification rather than a trade-success notification

#### Scenario: First rebalance right after a build is skipped

- **WHEN** the first rebalance after a build runs, with the allocated capital already deployed into positions and only the reserved cash buffer remaining
- **THEN** the planned run SHALL be buy-only with no deployable cash and the system SHALL skip it, submitting no orders and sending the informational skip notification

#### Scenario: Buy-only plan with deployable cash still runs

- **WHEN** a rebalance plans only buy intents (no sells) and the session holds unallocated cash beyond the reserved buffer
- **THEN** the system SHALL proceed with the run and deploy the cash into the planned buys

#### Scenario: Plan with a sell still runs

- **WHEN** a rebalance plans at least one sell intent
- **THEN** the system SHALL proceed with the run regardless of deployable cash

### Requirement: Notify when a selected session's rebalance is skipped

When a session's scheduled rebalance is actually engaged (the session was selected for the run) but the run is then skipped as a no-op, the system SHALL send one informational Pushover notification for that session naming the session's portfolio and the reason it was skipped, so the user is informed that the scheduled rebalance did nothing and why. This SHALL cover both the pre-agent crypto-only skip (no crypto to act on and no deployable cash to buy crypto) and the post-plan buy-only skip (no sells and no deployable cash, including the first rebalance after a build), on weekdays and weekends alike. This notification is informational and is distinct from the trade-success notification sent when a rebalance executes orders.

The system SHALL NOT send any notification for a session that was never engaged by the run — specifically a session excluded from the weekend crypto rebalance for not being crypto-scoped, and a stocks-only session skipped on a weekend end-of-day snapshot. Informing happens only when there was processing to report.

#### Scenario: Skipped crypto-only run informs the user

- **WHEN** a crypto-only rebalance for a selected session is skipped because it holds no crypto and has no deployable cash to buy crypto
- **THEN** the system SHALL send one informational notification naming the session's portfolio and the skip reason

#### Scenario: Skipped buy-only run informs the user

- **WHEN** a rebalance for a selected session is skipped because its plan is buy-only with no deployable cash (including the first rebalance after a build)
- **THEN** the system SHALL send one informational notification naming the session's portfolio and the skip reason

#### Scenario: Excluded and snapshot-skipped sessions stay silent

- **WHEN** a session is excluded from the weekend crypto rebalance for not being crypto-scoped, or a stocks-only session is skipped on a weekend end-of-day snapshot
- **THEN** the system SHALL send no notification for that session

### Requirement: Browse AI run history and details

The system SHALL let a client list AI runs (build and rebalance events) across all sessions, ordered newest first, with pagination and optional filtering by run type and status, and SHALL return a total count for the applied filter. The system SHALL let a client open a single AI run by its identifier and receive that run's detail: the run's reasoning output and research transcript, the trades it opened, and the positions it closed (the trades and closed positions referencing that run). Requesting an unknown run identifier SHALL return a not-found error.

#### Scenario: List runs across sessions

- **WHEN** a client requests the AI run list
- **THEN** the system SHALL return AI runs across all sessions ordered newest first, honoring pagination and any type/status filter, together with the matching total count

#### Scenario: Open a run's detail

- **WHEN** a client requests a run by its identifier
- **THEN** the system SHALL return the run's reasoning, its research transcript, the trades it opened, and the positions it closed

#### Scenario: Unknown run

- **WHEN** a client requests a run identifier that does not exist
- **THEN** the system SHALL return a not-found error

### Requirement: Maintain a per-session open-position ledger

The system SHALL maintain, per paper-trading session, a ledger of its currently open
positions — one entry per held ticker carrying the open quantity, a weighted-average
cost basis, and the date the position was opened. This ledger SHALL be the source of
truth for what a session holds and at what cost. The system SHALL NOT determine a
session's holdings by intersecting account-wide brokerage positions with the
portfolio's ticker list; the brokerage SHALL be used only to submit orders and to
price positions.

Every executed fill SHALL update the ledger: a buy SHALL open a new ledger entry or
increase an existing entry's quantity and re-compute its weighted-average cost from
the filled price; a sell SHALL reduce the entry's quantity and, when the position is
fully exited, remove the entry. A session's holdings SHALL be attributed to that
session alone, so two sessions holding the same ticker SHALL each track their own
quantity and cost basis independently.

Rebalance SHALL compute its share deltas from the ledger's current quantities, and
close SHALL liquidate the positions recorded in the ledger. Realized profit and loss
recorded when a position is exited SHALL use the ledger entry's average cost as the
entry price and its opened date as the entry date.

#### Scenario: Buy opens or increases a ledger entry

- **WHEN** a build or rebalance executes a buy fill for a session
- **THEN** the system SHALL create the session's ledger entry for that ticker, or
  increase its quantity and re-compute its weighted-average cost from the filled price

#### Scenario: Sell reduces or closes a ledger entry

- **WHEN** a rebalance or close executes a sell fill for a session
- **THEN** the system SHALL reduce that ledger entry's quantity and remove the entry
  when the position is fully exited

#### Scenario: Holdings are attributed per session

- **WHEN** two sessions each hold the same ticker
- **THEN** each session's ledger SHALL reflect only its own quantity and cost basis,
  independent of the other session and of the account-wide brokerage position

#### Scenario: Rebalance and close read the ledger

- **WHEN** a rebalance computes deltas or a close liquidates positions
- **THEN** the system SHALL use the session's ledger quantities as the current
  holdings, not the account-wide brokerage positions

#### Scenario: Realized P&L uses ledger basis

- **WHEN** a position is exited
- **THEN** the recorded realized profit and loss SHALL use the ledger entry's average
  cost as the entry price and its opened date as the entry date

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

### Requirement: Archive a stopped paper-trading session

The system SHALL let a client archive a paper-trading session and later unarchive
it. Archiving SHALL be a reversible, non-destructive state: an archived session
retains all of its data (trades, runs, positions, events, value snapshots) and can
be restored. A session SHALL be considered archived when, and only when, it carries
an archive timestamp.

The system SHALL allow archiving only a session whose status is stopped; a request
to archive an active or paused session SHALL be rejected without changing the
session. Unarchiving SHALL clear the archive timestamp and SHALL be allowed for any
archived session regardless of its status. Archiving or unarchiving an unknown
session SHALL respond 404.

Archiving and unarchiving SHALL change only the session's archived state; they SHALL
NOT alter the session's status or delete any related data.

#### Scenario: Archive a stopped session

- **WHEN** a client archives a session whose status is stopped
- **THEN** the system SHALL mark the session archived and retain all of its trades,
  runs, positions, events, and value snapshots

#### Scenario: Reject archiving a non-stopped session

- **WHEN** a client attempts to archive a session whose status is active or paused
- **THEN** the system SHALL reject the request and SHALL leave the session
  unarchived

#### Scenario: Unarchive a session

- **WHEN** a client unarchives an archived session
- **THEN** the system SHALL clear its archived state and return it to the default
  session list, without changing its status

#### Scenario: Archive an unknown session

- **WHEN** a client archives or unarchives a session id that does not exist
- **THEN** the system SHALL respond 404

### Requirement: Archive-aware session listing

The system SHALL exclude archived sessions from the default session list, and SHALL
provide a way to include archived sessions on request. When archived sessions are
included, each session returned SHALL carry its archived state so a client can
distinguish archived from active rows. The archived filter SHALL compose with the
existing status filter.

#### Scenario: Default list hides archived sessions

- **WHEN** a client lists paper-trading sessions without asking for archived rows
- **THEN** the system SHALL return only sessions that are not archived

#### Scenario: Include archived sessions on request

- **WHEN** a client lists paper-trading sessions and opts to include archived rows
- **THEN** the system SHALL return both archived and non-archived sessions, each
  indicating its archived state

### Requirement: Reconcile a session's order status against the broker

The system SHALL reconcile a paper-trading session's recorded trades against the
broker until each trade reaches a terminal order status. For each of the session's
trades that carries a broker order id and whose recorded order status is not yet
terminal, the system SHALL query the broker for the current state of that order and
SHALL update the trade's recorded order status, filled price, and filled time to
match the broker's current values. Terminal order statuses (filled, cancelled,
rejected) SHALL NOT be re-queried, and a trade without a broker order id SHALL be
left unchanged.

If the broker cannot be reached or does not recognise an order, that trade SHALL be
left unchanged and reconciliation of the remaining trades SHALL continue; a
transient broker failure SHALL NOT corrupt or discard already-recorded trade data.

Reconciling an unknown session SHALL respond 404.

#### Scenario: A pending order fills

- **WHEN** a session is reconciled and one of its trades — recorded as non-terminal
  — is now reported by the broker as filled at a known price and time
- **THEN** the system SHALL update that trade's order status to filled and record
  the broker's fill price and fill time

#### Scenario: Terminal trades are not re-queried

- **WHEN** a session is reconciled and a trade is already in a terminal order status
- **THEN** the system SHALL leave that trade unchanged and SHALL NOT query the broker
  for it

#### Scenario: A trade without a broker order id is skipped

- **WHEN** a session is reconciled and a non-terminal trade has no broker order id
- **THEN** the system SHALL leave that trade unchanged

#### Scenario: Broker unavailable during reconciliation

- **WHEN** the broker cannot be reached or does not recognise an order while a session
  is being reconciled
- **THEN** the system SHALL leave the affected trade unchanged, SHALL continue
  reconciling the session's other trades, and SHALL NOT discard existing trade data

#### Scenario: Reconcile an unknown session

- **WHEN** a client reconciles a session id that does not exist
- **THEN** the system SHALL respond 404

### Requirement: Correct ledger cost basis from actual fills

When reconciliation of a buy trade produces a fill price that differs from the price
recorded for that trade at submission, the system SHALL correct the session's
open-position cost basis for that ticker so that the position's average cost reflects
the actual fill price rather than the pre-trade estimate. If the reconciled fill
price equals the previously recorded price, the cost basis SHALL be left unchanged.

#### Scenario: Fill price differs from the submitted estimate

- **WHEN** a buy trade is reconciled and the broker's actual fill price differs from
  the price recorded for that trade at submission, and the ticker is still held
- **THEN** the system SHALL adjust the open position's average cost so it reflects the
  actual fill price

#### Scenario: Fill price matches the estimate

- **WHEN** a buy trade is reconciled and the broker's fill price equals the price
  already recorded for that trade
- **THEN** the system SHALL leave the open position's cost basis unchanged

### Requirement: Scheduled reconciliation of all sessions' open orders

The system SHALL provide a scheduled entry point that reconciles the non-terminal
orders of every paper-trading session, so that order state and cost basis resolve
even when no client is viewing a session. This entry point SHALL be protected by the
same cron authorization used by other scheduled operations and SHALL reject requests
lacking a valid cron token. A failure to reconcile one session SHALL NOT prevent the
remaining sessions from being reconciled, and the operation SHALL report how many
sessions and trades were reconciled.

#### Scenario: Cron reconciles open orders across sessions

- **WHEN** the scheduled reconciliation entry point is invoked with a valid cron token
- **THEN** the system SHALL reconcile the non-terminal orders of all sessions and
  SHALL report the sessions and trades it reconciled

#### Scenario: Cron request without a valid token is rejected

- **WHEN** the scheduled reconciliation entry point is invoked without a valid cron
  token
- **THEN** the system SHALL reject the request and SHALL NOT reconcile any session

#### Scenario: One session's failure does not stop the rest

- **WHEN** reconciling one session fails during a scheduled run
- **THEN** the system SHALL continue reconciling the remaining sessions

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

### Requirement: Versioned rebalancing prompt stored in the database

The AI rebalance flow SHALL obtain its prompt from a versioned prompt record
persisted in the database rather than from a value hardcoded in application code.
A prompt record SHALL comprise two parts: the agent **instructions** (the system
persona and requirements) and the run **input template** (the per-run message the
agent is given), each stored as a text template that preserves the runtime
placeholders the flow fills in (the reasoning/discovery caps in the instructions;
the risk profile, current holdings, account summary, and candidate universe in
the input template).

Prompt records SHALL be append-only and identified by a monotonically increasing
integer version. The **active** prompt SHALL be the record with the highest
version. Each AI-managed paper-trading session SHALL **freeze** a rebalance prompt
version: when the session is built, the version that is active at that time SHALL
be captured and stored on the session as a required (non-nullable) value, and
every subsequent rebalance for that session SHALL use that frozen version — not
whatever is active later — so that adding a newer prompt version does not change
the behavior of sessions already built. Existing sessions that predate per-session
freezing SHALL be migrated to the highest prompt version that exists at migration
time, so that every session has a frozen version and no runtime fallback is
required. When a rebalance runs, the system SHALL load the session's frozen prompt
version, fill its placeholders with the run's values, and use the result as the
agent's instructions and input; the rendered values SHALL be identical to those
produced by the previously hardcoded prompt for the same inputs. If the frozen
prompt version cannot be found in the database, the rebalance SHALL fail with a
clear error rather than running against an empty prompt.

The initial deploy SHALL seed version 1 with the prompt text that is in use at
the time versioning was introduced, so that behavior is unchanged on first run.
Adding a new prompt version (a new record with a higher version) SHALL change the
prompt used by sessions built **after** it becomes active, without any code
change, while leaving already-built sessions on their frozen version. The frozen
version SHALL be observable on the session's read model. This requirement covers
the rebalance prompt only; the AI build prompt is unaffected.

#### Scenario: A session freezes the active version at build time

- **WHEN** an AI build creates a paper-trading session and version N is the active
  rebalance prompt
- **THEN** the system SHALL store N as the session's frozen rebalance prompt
  version
- **AND** the frozen version SHALL be readable on the session's read model

#### Scenario: Rebalance uses the session's frozen version

- **WHEN** an AI rebalance runs for a session whose frozen prompt version is N
- **AND** newer prompt versions exist
- **THEN** the system SHALL use version N as the rebalance prompt
- **AND** SHALL fill its placeholders with the run's risk profile, holdings,
  account summary, and candidate universe before invoking the agent

#### Scenario: Rebalance uses the active (highest-version) prompt

- **WHEN** existing sessions are migrated to per-session freezing
- **THEN** each session SHALL be frozen to the highest prompt version that exists
  at migration time
- **AND** subsequent rebalances for those sessions SHALL use that frozen version

#### Scenario: A newer version supersedes the previous prompt

- **WHEN** a new prompt record is added with a version higher than the current
  active version
- **THEN** sessions built after it becomes active SHALL freeze and use the new
  record's instructions and input template
- **AND** sessions already built SHALL keep using their frozen version
- **AND** the previous version SHALL remain stored and unchanged

#### Scenario: Seeded first version preserves current behavior

- **WHEN** prompt versioning is first deployed and no prompt has been edited
- **THEN** the active prompt SHALL be the seeded version 1
- **AND** the instructions and input it produces for a given run SHALL match the
  text the previously hardcoded prompt produced for the same inputs

#### Scenario: No prompt available

- **WHEN** an AI rebalance runs and the session's frozen prompt version cannot be
  found in the database
- **THEN** the system SHALL fail the rebalance with an explicit error indicating
  the rebalance prompt is missing
- **AND** SHALL NOT invoke the agent with an empty prompt

### Requirement: Per-trade transaction cost

The system SHALL charge a fixed transaction cost on every executed trade it
records for a paper-trading session, regardless of side (buy or sell). The cost
per trade SHALL be a single configurable amount (defaulting to one US dollar) and
SHALL be applied at the single point where a trade is recorded, so that no trade
can be recorded without incurring the cost. The system SHALL accumulate these
costs per session as a cumulative, non-negative transaction-fees total.

A session's current portfolio value SHALL be net of its cumulative transaction
fees: the value SHALL equal the allocated capital plus cumulative realised
profit/loss, minus cumulative transaction fees, plus live unrealised profit/loss
on open positions. Consequently the cash portion of the valuation and the daily
value snapshots SHALL reflect fees paid. The realised profit/loss recorded on an
individual closed position SHALL remain gross (derived from entry and exit prices
only) — transaction fees SHALL be tracked at the session level rather than folded
into per-position realised profit/loss.

The transaction cost SHALL apply going forward only: sessions that predate this
capability SHALL begin with a cumulative fees total of zero and SHALL NOT have
historical trades re-priced. New trades on any session, old or new, SHALL incur
the cost from this point on.

#### Scenario: Recording a trade charges the cost

- **WHEN** the system records an executed trade for a session
- **THEN** the session's cumulative transaction fees SHALL increase by the
  configured per-trade cost
- **AND** a session that executes two trades in a run SHALL accrue twice the
  per-trade cost

#### Scenario: Portfolio value is net of fees

- **WHEN** the system values a session that has accrued transaction fees
- **THEN** the reported current portfolio value SHALL subtract the session's
  cumulative transaction fees from what it would otherwise be

#### Scenario: Closed-position realised P&L stays gross

- **WHEN** a position is exited and its realised profit/loss is recorded
- **THEN** that per-position realised profit/loss SHALL be derived from entry and
  exit prices only and SHALL NOT be reduced by the transaction cost

#### Scenario: Existing sessions start at zero fees

- **WHEN** the transaction-cost capability is first deployed
- **THEN** every existing session SHALL have a cumulative transaction-fees total of
  zero and its already-recorded trades SHALL NOT be retroactively charged

### Requirement: Rebalancing prompt informs the agent of transaction costs

The active rebalance prompt SHALL inform the agent that each executed trade incurs
a fixed transaction cost, so that the agent avoids churning small positions when
the expected benefit is below the cost of trading. This SHALL be delivered as a
new rebalance prompt version (per the versioned-prompt requirement); sessions
built after it becomes active SHALL freeze and use it, while already-built
sessions keep their frozen version.

#### Scenario: New sessions freeze the cost-aware prompt

- **WHEN** an AI build creates a session after the cost-aware rebalance prompt
  becomes the active version
- **THEN** the session SHALL freeze that version
- **AND** its rebalances SHALL present the agent with instructions that describe
  the per-trade transaction cost

### Requirement: Rebalancing prompt drives the trend-trading strategy

The active rebalance prompt SHALL instruct the agent to trade trend using the
technical context supplied per run, delivered as a new rebalance prompt version
(per the versioned-prompt requirement); sessions built after it becomes active
SHALL freeze and use it, while already-built sessions keep their frozen version.
The prompt SHALL give two-part instructions: (1) allocate among the supplied
candidates — which have already been hard-filtered to confirmed uptrends — by
conviction, using their trend indicators; and (2) for each current holding, judge
whether to sell, trim, or hold from its supplied indicator set and reversal flags.
The prompt SHALL retain the existing constraints (long-only, target weights sum to
approximately 1.0, per-trade transaction-cost discipline, crypto handled with
around-the-clock tickers, discovery and web-search caps) and SHALL NOT change the
AI output schema — omitting a holding or giving it an allocation of ~0 still means
sell/exit.

#### Scenario: New sessions freeze the trend-trading prompt

- **WHEN** an AI build creates a session after the trend-trading rebalance prompt becomes the active version
- **THEN** the session SHALL freeze that version
- **AND** its rebalances SHALL present the agent with instructions to allocate among trend-confirmed candidates and to judge each holding's sell/trim/hold from its technical indicators and reversal flags

#### Scenario: Trend-trading prompt preserves the output contract

- **WHEN** the trend-trading rebalance prompt is used for a run
- **THEN** the agent SHALL still return long-only target allocations summing to approximately 1.0, with an omitted or ~0-weight holding meaning exit, unchanged from the prior prompt version's output schema

### Requirement: Record and expose per-run trend-decision context

The system SHALL persist, per AI build or rebalance run **of a session that opted into the technical-indicator trend strategy**, the trend-decision context that shaped the candidates and holdings presented to the AI: the candidates that were **dropped by the trend gate** — each with its ticker and the reason it failed (which gate condition, or that it had no stored snapshot) — and the **indicator annotations handed to the AI** for the surviving candidates and for the current holdings (the indicator values and, for holdings, the reversal flags). This context SHALL be recorded on the AI-portfolio event alongside the run's reasoning and research transcript, and SHALL be captured best-effort so that a run which fails after the candidate/holdings assembly still persists the context gathered before the failure. A build run (which has no prior holdings) SHALL record the dropped candidates and the surviving-candidate annotations, with an empty holdings section. When a run performed no gating — because the session did not opt into the trend strategy (including a session frozen to a pre-trend prompt version) — the trend-decision context SHALL be absent (null) rather than fabricated.

The system SHALL include the persisted trend-decision context in the run detail returned for a single AI run, so a client can show what was filtered out and what was handed to the AI.

#### Scenario: Build records its trend-decision context

- **WHEN** an AI build of an opted-in session assembles its candidate universe under the trend gate
- **THEN** the recorded build event SHALL persist the candidates dropped by the gate (each with its reason) and the indicator annotations for the surviving candidates

#### Scenario: Rebalance records candidates and holdings context

- **WHEN** an AI rebalance of an opted-in session assembles candidates and holdings
- **THEN** the recorded rebalance event SHALL persist the dropped candidates with reasons, the surviving-candidate indicator annotations, and each holding's indicator values and reversal flags

#### Scenario: No context recorded for an opted-out session

- **WHEN** an AI run executes for a session that did not opt into the trend strategy
- **THEN** the recorded event SHALL persist no trend-decision context (absent)

#### Scenario: Context captured despite a mid-run failure

- **WHEN** an AI run of an opted-in session fails after candidate/holdings assembly but before completion
- **THEN** the recorded (failed) event SHALL still persist the trend-decision context gathered before the failure

#### Scenario: Run detail returns the trend-decision context

- **WHEN** a client requests a single AI run's detail
- **THEN** the returned detail SHALL include the run's persisted trend-decision context (dropped candidates with reasons and the indicator annotations handed to the AI), or absent when the run recorded none

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

### Requirement: Multi-session comparison value history read

The system SHALL provide a read that returns, in a single response, the value history of multiple paper-trading sessions so they can be compared over time. The response SHALL include **every non-archived session** (active, paused, or stopped) — the same set as the default session listing, excluding soft-archived sessions. For each included session the response SHALL carry: a stable session identifier, a display **label** (the session's portfolio name, falling back to its strategy key when the portfolio name is unresolved), its **allocated capital**, and its ordered list of value **points** — each point exposing at least the snapshot date and the session's total portfolio value on that date — sorted oldest date first. A session that has no value snapshots yet SHALL still be included with an empty points list. The read SHALL NOT require or accept a per-session identifier as input (it returns the comparison set as a whole).

#### Scenario: Comparison read returns each non-archived session's series

- **WHEN** a client requests the multi-session comparison value history and multiple non-archived sessions exist, each with value snapshots
- **THEN** the response SHALL contain one entry per non-archived session, each carrying the session's identifier, label, allocated capital, and its value points ordered oldest date first

#### Scenario: Archived sessions are excluded

- **WHEN** a client requests the multi-session comparison value history and one or more sessions are archived
- **THEN** the response SHALL omit every archived session and include only the non-archived ones

#### Scenario: Session without snapshots is included with no points

- **WHEN** a client requests the multi-session comparison value history and a non-archived session has no value snapshots yet
- **THEN** the response SHALL still include that session with its identifier, label, and allocated capital, and an empty list of points

#### Scenario: Session label falls back to the strategy key

- **WHEN** a session in the comparison read has no resolvable portfolio name
- **THEN** that session's label SHALL be its strategy key rather than an empty value

### Requirement: Session risk and trade-effectiveness KPIs

The per-session KPI read SHALL additionally report a session's maximum drawdown, win rate, average win, average loss, best trade, and worst trade, each computed on read from data already recorded for the session and reported as absent (null) when its inputs are insufficient.

**Maximum drawdown** SHALL be the largest peak-to-trough decline in the session's portfolio value, expressed as a non-negative fraction of the running peak, computed over the session's daily value-snapshot series ordered by date: tracking the running maximum value and the deepest proportional drop below it. It SHALL be reported as absent when the session has no value snapshots, and SHALL be zero when the value series only ever rose (never declined below a prior peak).

**Win rate** SHALL be the fraction of the session's closed positions whose realized profit-and-loss is strictly greater than zero, expressed in [0, 1]. It SHALL be reported as absent when the session has no closed positions.

**Average win** SHALL be the mean realized profit-and-loss of the session's closed positions with realized P&L strictly greater than zero, and **average loss** SHALL be the mean realized profit-and-loss of the session's closed positions with realized P&L strictly less than zero. Average win SHALL be reported as absent when the session has no winning closed positions; average loss SHALL be reported as absent when it has no losing closed positions.

**Best trade** SHALL be the maximum, and **worst trade** the minimum, realized profit-and-loss across the session's closed positions. Both SHALL be reported as absent when the session has no closed positions.

These figures SHALL NOT change how value snapshots or closed positions are recorded, and SHALL require no new stored fields.

#### Scenario: Maximum drawdown from the value series

- **WHEN** the KPIs are read for a session whose daily value snapshots rise to a peak and then decline before partially recovering
- **THEN** the read SHALL report the maximum drawdown as the deepest peak-to-trough decline expressed as a fraction of the running peak

#### Scenario: Drawdown is zero for a monotonically rising series

- **WHEN** the KPIs are read for a session whose value snapshots never fall below a prior peak
- **THEN** the read SHALL report a maximum drawdown of zero

#### Scenario: Drawdown absent without snapshots

- **WHEN** the KPIs are read for a session that has no value snapshots
- **THEN** the read SHALL report the maximum drawdown as absent

#### Scenario: Win rate and trade averages from closed positions

- **WHEN** the KPIs are read for a session with a mix of winning and losing closed positions
- **THEN** the read SHALL report the win rate as the fraction of closed positions with realized P&L above zero, the average win as the mean realized P&L of the winners, the average loss as the mean realized P&L of the losers, the best trade as the maximum realized P&L, and the worst trade as the minimum realized P&L

#### Scenario: Trade metrics absent without closed positions

- **WHEN** the KPIs are read for a session that has no closed positions
- **THEN** the read SHALL report win rate, average win, average loss, best trade, and worst trade all as absent

#### Scenario: Average win or average loss absent when one side is empty

- **WHEN** the KPIs are read for a session whose closed positions are all winners (or all losers)
- **THEN** the read SHALL report a win rate and the populated side's average, and SHALL report the empty side's average (average loss when all winners, or average win when all losers) as absent

### Requirement: Rebalance sizes against the session's current value

An automated rebalance SHALL size its target weights against the session's **current
marked-to-market value** — the allocated capital adjusted by cumulative realised
profit/loss and transaction fees plus the live unrealised profit/loss of open positions,
equivalently the current market value of all open positions plus the session's
unallocated cash — rather than against the session's original frozen allocated capital,
**reduced by the reserved cash buffer** (see "Reserve a cash buffer when sizing orders").
The normalised target weights (which sum to approximately one, after any guardrail
enforcement) SHALL therefore be applied to the session's current equity net of the
reserved buffer, so that each target position value is a fraction of what the session is
worth now less the reserve. Realised and unrealised gains SHALL thereby be redeployed into
the target allocation on the next rebalance, and after losses the targets SHALL be sized to
the session's reduced equity rather than its original capital.

The target-weight delta model SHALL be otherwise unchanged: the system SHALL still trade
only the delta between each target position and the current position (a buy when the
target exceeds the current holding, a sell or full exit when it falls short), SHALL still
apply fractional sizing for crypto and whole-share sizing for equities, and SHALL still
enforce any configured risk guardrails on the weight vector before sizing.

The **initial build** SHALL continue to size positions against the session's allocated
capital (likewise reduced by the reserved cash buffer). Because at build time the session
holds no positions and has no profit/loss, its current value equals its allocated capital,
so build sizing is unaffected apart from the reserve; only the rebalance seam uses the
current-value base.

#### Scenario: Gains are redeployed on rebalance

- **WHEN** a session whose current value has grown above its allocated capital is
  rebalanced
- **THEN** the system SHALL size the target positions against the current (grown) value,
  so the gains are deployed into the target allocation rather than left idle as cash

#### Scenario: Targets sized down after losses

- **WHEN** a session whose current value has fallen below its allocated capital is
  rebalanced
- **THEN** the system SHALL size the target positions against the current (reduced)
  value rather than the original allocated capital

#### Scenario: Build still sizes against allocated capital

- **WHEN** a portfolio is first built (no positions, no profit/loss yet)
- **THEN** the system SHALL size the initial positions against the allocated capital,
  which equals the session's current value at that moment

#### Scenario: Sizing base is net of the reserved buffer

- **WHEN** a rebalance sizes positions against the current value
- **THEN** the system SHALL first reduce that value by the reserved cash buffer and apply
  the target weights to the net base, so the session retains a cash reserve for fees and
  slippage

#### Scenario: Delta model and guardrails unchanged

- **WHEN** a rebalance sizes positions against the current value
- **THEN** the system SHALL still trade only the delta between target and current
  positions and SHALL still enforce any configured risk guardrails on the target weights
  before sizing

### Requirement: Reserve a cash buffer when sizing orders

The AI executor SHALL reserve a **cash buffer** before sizing build or rebalance
orders, so that executed buys cannot claim the full value available and the
session's **unallocated cash is not driven negative** by fully deploying value
plus per-trade transaction fees and market-order fill slippage.

The reserved buffer SHALL be the **greater of**:

1. a **configurable percentage** of the sizing base (the allocated capital at
   build, the session's current marked-to-market value at rebalance), and
2. the **estimated total transaction fees** for the run — the number of
   candidate orders for the run multiplied by the per-trade transaction cost.

The sizing base SHALL be reduced by the reserved buffer **before** any target
weight is applied, so every per-ticker allocation is sized against the net
(post-buffer) base. The reserve SHALL be applied consistently at both the
initial build and every rebalance, and SHALL apply to a crypto-only rebalance's
crypto-scoped base as well. When the per-trade transaction cost is zero and the
buffer percentage is zero, the reserve SHALL be zero and sizing SHALL be
unchanged.

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

- **WHEN** the estimated total fees for a run exceed the configured percentage of
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

- **WHEN** the per-trade transaction cost and the buffer percentage are both zero
- **THEN** the reserved buffer SHALL be zero and sizing SHALL match the behavior
  with no buffer

### Requirement: Rebalance submits sells before buys and gates buys on sell fills

During a rebalance, the system SHALL submit every sell (including full exits) before it submits any buy, and SHALL submit the buys only after the submitted sells have reached a terminal order state at the brokerage. Terminal states are filled, cancelled, and rejected; a cancelled or rejected sell counts as settled so it never blocks the run, and a rebalance with no sells to place SHALL proceed directly to its buys. The buys SHALL be submitted together once the sells have settled, rather than interleaved with the sells. This ordering guarantee holds regardless of the order in which tickers would otherwise be processed.

The wait for sells to settle SHALL be bounded by a configured timeout. If the timeout elapses before the submitted sells settle, the system SHALL NOT submit the dependent buys for that run; it SHALL record each withheld buy as not executed with a reason indicating the sells had not yet filled, and SHALL leave the executed sells in place so a later rebalance redeploys the freed cash. The system SHALL retry an order the brokerage rejects, up to a bounded number of attempts within the same run, before recording it as not executed.

All existing rebalance behavior SHALL be preserved: crypto-only scope, skipping equity orders while the equities market is closed, the risk-guardrail weight clamp, sizing against the session's current value, fractional crypto / whole-share equity sizing, and the recorded trade shape. When the brokerage fills orders synchronously (the offline stub), the submitted sells settle immediately and the buys proceed within the same run.

#### Scenario: Sells are submitted before any buy

- **WHEN** a rebalance needs to both sell some holdings and buy others
- **THEN** the system SHALL submit all of the sell orders before it submits any buy order

#### Scenario: Buys wait until sells have settled

- **WHEN** the sell orders have been submitted but have not yet reached a terminal state at the brokerage
- **THEN** the system SHALL withhold the buy orders until every submitted sell reaches a terminal state (filled, cancelled, or rejected)

#### Scenario: Synchronous broker completes the rebalance in one run

- **WHEN** the brokerage fills orders synchronously (the offline stub)
- **THEN** the submitted sells SHALL settle immediately and the system SHALL submit the buys in the same run, with the freed cash available to fund them

#### Scenario: Rebalance with no sells proceeds to buys

- **WHEN** a rebalance has only buy orders and no sells to place
- **THEN** the system SHALL submit the buys without waiting, since there is nothing to settle

#### Scenario: Fill-wait timeout withholds buys without failing the run

- **WHEN** the submitted sells do not settle before the configured fill-wait timeout elapses (for example, sells placed while the equities market is closed)
- **THEN** the system SHALL skip the dependent buys for that run, record each withheld buy as not executed with a "sells not yet filled" reason, and keep the executed sells so a later rebalance redeploys the freed cash

#### Scenario: Rejected order is retried

- **WHEN** the brokerage rejects a submitted order
- **THEN** the system SHALL resubmit it up to the bounded retry limit within the same run before recording it as not executed

### Requirement: Crypto-only rebalance scope

The system SHALL support a crypto-only rebalance that adjusts only a session's crypto
holdings and targets, leaving the session's equity positions untouched. When a
rebalance runs in crypto-only mode, the system SHALL restrict the candidate universe
and the holdings it acts on to crypto assets, regardless of the session's configured
asset scope, so that a session permitted to hold both equities and crypto still
rebalances only its crypto in this mode. The system SHALL NOT place any equity order
during a crypto-only rebalance, and SHALL NOT sell, trim, or add to equity positions.
Equity positions SHALL remain exactly as they were before the crypto-only run.

A crypto-only rebalance SHALL be recorded as skipped without invoking the agent when
the session has no crypto positions to act on and no deployable unallocated cash to buy
crypto (its free cash, net of the reserved cash buffer, is insufficient to fund a
crypto buy) — since it can then neither rotate existing crypto nor deploy cash into
crypto. This includes a crypto-scoped session (scope crypto or both) that currently
holds only equity shares and has no free capital. When the session holds crypto, or has
deployable cash to buy crypto, the run SHALL proceed.

#### Scenario: Mixed session rebalances only crypto

- **WHEN** a crypto-only rebalance runs for a session that holds both equities and
  crypto
- **THEN** the system SHALL place orders only for crypto assets and SHALL leave every
  equity position unchanged

#### Scenario: Candidates restricted to crypto

- **WHEN** the agent is invoked for a crypto-only rebalance
- **THEN** the candidate universe presented to the agent SHALL contain only crypto
  assets, even for a session whose asset scope permits equities

#### Scenario: No crypto means no agent run

- **WHEN** a crypto-only rebalance is requested for a session that neither holds nor
  targets any crypto
- **THEN** the system SHALL record the run as skipped and SHALL NOT invoke the agent

#### Scenario: Crypto-scoped session holding only shares with no free cash is skipped

- **WHEN** a crypto-only rebalance runs for a session whose configured scope includes
  crypto but which currently holds only equity shares and has no deployable unallocated
  cash to buy crypto
- **THEN** the system SHALL record the run as skipped without invoking the agent and
  SHALL place no orders, leaving the equity positions untouched

#### Scenario: Idle cash lets a crypto-scoped session deploy into crypto

- **WHEN** a crypto-only rebalance runs for a session whose configured scope includes
  crypto, holds no crypto yet, targets crypto, and has deployable unallocated cash
- **THEN** the system SHALL proceed with the run so the cash can be deployed into crypto

### Requirement: Crypto-only rebalance sizes against the crypto investable budget

In a crypto-only rebalance the system SHALL size crypto target weights against the
session's **crypto investable budget**, defined as the current market value of the
session's crypto positions plus the session's unallocated (free) cash — not against
the session's full allocated capital. The unallocated cash SHALL be the session's
derived free cash (allocated capital adjusted by realised profit/loss and fees, plus
unrealised position value, less the market value of all open positions). Sizing
against this budget SHALL allow the run both to rotate capital between existing crypto
positions and to deploy idle cash into crypto, while never drawing on capital tied up
in equity positions. The crypto-only run SHALL NOT size any position against the full
allocated capital.

#### Scenario: Weights applied to the crypto budget, not total capital

- **WHEN** a crypto-only rebalance sizes a crypto target for a session that also holds
  equities
- **THEN** the system SHALL compute the target position value from the crypto
  investable budget (crypto positions' market value plus unallocated cash), not from
  the session's full allocated capital

#### Scenario: Idle cash can be deployed into crypto

- **WHEN** a crypto-only rebalance runs for a session that holds unallocated cash and
  targets a larger crypto allocation
- **THEN** the system SHALL be able to buy crypto up to the crypto investable budget,
  including the unallocated cash

#### Scenario: Equity capital is never used for crypto

- **WHEN** a crypto-only rebalance sizes crypto positions
- **THEN** the capital tied up in the session's equity positions SHALL NOT be included
  in the crypto investable budget

### Requirement: Rebalance agent informed of the session's unallocated cash

The system SHALL provide the rebalance agent with the session's own derived
unallocated (free) cash in the account summary it receives, rather than a global or
broker-wide cash figure that does not reflect the individual session's capital. For a
crypto-only rebalance the account summary SHALL additionally convey the crypto
investable budget the agent's crypto weights will be sized against. The cash figure
presented to the agent SHALL be the session-derived unallocated cash described in
"Crypto-only rebalance sizes against the crypto investable budget".

#### Scenario: Account summary carries session cash

- **WHEN** the rebalance agent is invoked for a session
- **THEN** the account summary SHALL report the session's own derived unallocated
  cash rather than a shared broker-wide buying-power figure

#### Scenario: Crypto budget conveyed for crypto-only runs

- **WHEN** the rebalance agent is invoked for a crypto-only rebalance
- **THEN** the account summary SHALL additionally convey the crypto investable budget
  (crypto positions' market value plus unallocated cash)

### Requirement: Crypto-only rebalance uses a crypto-scoped prompt

A crypto-only rebalance SHALL use a rebalance prompt whose instructions make clear
that the agent is rebalancing only the session's crypto sleeve within the provided
crypto investable budget, and that equities will not be traded in this run. This
crypto-scoped prompt SHALL be stored as a versioned rebalance-prompt record under the
same versioning rules as the standard rebalance prompt (see "Versioned rebalancing
prompt stored in the database"); it SHALL NOT be a prompt hardcoded in application
code. A crypto-only run SHALL fail with a clear error, rather than invoking the agent
with an empty prompt, if its crypto-scoped prompt cannot be found.

#### Scenario: Crypto-only run uses the crypto-scoped prompt

- **WHEN** a crypto-only rebalance invokes the agent
- **THEN** the system SHALL use the crypto-scoped rebalance prompt, instructing the
  agent that only the crypto sleeve is being rebalanced within the crypto investable
  budget

#### Scenario: Missing crypto prompt fails cleanly

- **WHEN** a crypto-only rebalance runs and its crypto-scoped prompt cannot be found
- **THEN** the system SHALL fail the rebalance with an explicit error and SHALL NOT
  invoke the agent with an empty prompt

### Requirement: Per-session sector and category performance breakdown

The system SHALL expose, on demand for a given paper-trading session, a breakdown of
the session's performance grouped both by the held assets' **sector** and by their
**category**. For each group the system SHALL report: the cumulative realised
profit/loss of positions closed in that group, the live unrealised profit/loss of the
session's open positions in that group (marked to market at request time), the total
profit/loss of the group (realised plus unrealised), the current market value of the
group's open positions, and the group's return as a fraction (the group's total
profit/loss divided by the group's invested cost basis). When a group's invested cost
basis is zero the return SHALL be reported as unavailable (no value) rather than
failing the request or dividing by zero.

Grouping SHALL be resolved by joining the session's open and closed positions to the
asset catalogue on a normalised ticker (matching the catalogue's canonical casing). An
asset whose sector is not set (for example crypto and most funds) SHALL be grouped
under a dedicated "no sector" bucket in the by-sector breakdown; its category is still
used for the by-category breakdown. A position whose ticker no longer matches any
catalogue asset SHALL be grouped under a dedicated "unknown" bucket in both
breakdowns, so the breakdown never silently drops profit/loss. Every unit of the
session's realised and unrealised profit/loss SHALL be attributed to exactly one group
in each breakdown. A request for an unknown session SHALL fail as not found.

#### Scenario: Breakdown grouped by sector and category

- **WHEN** a client requests the sector/category performance breakdown for an existing
  session
- **THEN** the system SHALL return two groupings — one keyed by sector and one keyed by
  category — each listing, per group, the realised P&L, unrealised P&L, total P&L,
  market value, and return fraction

#### Scenario: Total P&L combines realised and unrealised

- **WHEN** a group contains both closed positions and open positions
- **THEN** the group's total P&L SHALL equal its realised P&L (from closed positions)
  plus its unrealised P&L (from open positions marked to market at request time)

#### Scenario: Open positions marked to market

- **WHEN** the breakdown is computed for a session with open positions
- **THEN** each open position's unrealised P&L and market value SHALL be valued against
  current quotes at request time rather than a stale stored valuation

#### Scenario: Assets without a sector are bucketed

- **WHEN** the session holds or has closed an asset that has no sector (such as crypto)
- **THEN** that asset's performance SHALL be attributed to a dedicated "no sector"
  bucket in the by-sector breakdown while still being attributed to its own category in
  the by-category breakdown

#### Scenario: Unknown tickers are bucketed, not dropped

- **WHEN** a session position's ticker does not match any catalogue asset
- **THEN** that position's performance SHALL be attributed to a dedicated "unknown"
  bucket in both breakdowns rather than being omitted

#### Scenario: Group return guards divide-by-zero

- **WHEN** a group's invested cost basis is zero
- **THEN** the group's return SHALL be reported as unavailable rather than failing the
  request

#### Scenario: Unknown session

- **WHEN** a client requests the breakdown for a session id that does not exist
- **THEN** the system SHALL respond with a not-found error and no breakdown

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

### Requirement: Redeploy unexecutable target weight across executable targets

During an automated rebalance, when one or more of the AI's target positions cannot be
executed, the system SHALL redistribute the unexecuted targets' weight across the targets
that **can** be executed, rather than leaving that weight uninvested as cash. A target is
**unexecutable** for the run when the broker returns no usable price for it, or when its
share of the sizing base cannot fund the minimum tradable amount for its asset class (at
least one whole share for an equity, or the minimum crypto notional for a crypto asset).

The redeployment SHALL remain bounded by the reserved cash buffer (see "Reserve a cash
buffer when sizing orders"): the system SHALL NOT deploy capital below the reserved buffer,
so the session still retains its cash reserve for fees and slippage. When a session has
risk guardrails enabled, the redeployed weight vector SHALL still satisfy the configured
guardrail caps (per-asset, per-asset-class, and maximum invested fraction); weight that
cannot be placed without breaching a guardrail SHALL remain as cash, consistent with the
guardrail requirements. The redeployment SHALL preserve the existing delta model: the
system still trades only the delta between each resulting target position and the current
position, still uses whole-share sizing for equities and fractional sizing for crypto, and
still submits sells before buys.

When every target is unexecutable, or no executable target can absorb additional weight
without breaching the cash buffer or a guardrail, the system SHALL leave the residual as
cash rather than failing the run.

#### Scenario: An unpriceable target's weight is redeployed

- **WHEN** a rebalance has several target positions and one target cannot be priced by the
  broker
- **THEN** the system SHALL redistribute that target's weight across the targets that can
  be priced and executed, so the session's invested fraction reflects the executable
  targets rather than stranding the unpriceable target's weight as cash

#### Scenario: A target too small for one share is redeployed

- **WHEN** a target position's share of the sizing base cannot fund even one whole share of
  that equity (or the minimum crypto notional for a crypto target)
- **THEN** the system SHALL redistribute that target's weight across the targets that can be
  funded, rather than silently leaving that slice of capital uninvested

#### Scenario: Redeployment respects the reserved cash buffer

- **WHEN** unexecutable target weight is redeployed across the executable targets
- **THEN** the system SHALL NOT deploy capital below the reserved cash buffer, so the
  session still retains its cash reserve for fees and slippage

#### Scenario: Redeployment respects risk guardrails when enabled

- **WHEN** a session with risk guardrails enabled has unexecutable target weight to redeploy
- **THEN** the resulting target weights SHALL still satisfy the per-asset, per-asset-class,
  and maximum-invested guardrail caps, and any weight that cannot be placed without
  breaching a cap SHALL remain as cash

#### Scenario: All targets unexecutable leaves cash without failing

- **WHEN** no target in a rebalance can be executed (for example, none can be priced)
- **THEN** the system SHALL leave the capital as cash and complete the run without error,
  recording each target as not executed

### Requirement: Record a rebalance target that cannot be executed

When a rebalance cannot execute a target position, the system SHALL record that target as a
non-executed outcome with a clear reason (for example, that no price was available, or that
the target was too small to fund the minimum tradable amount), so that a `partial`-status
run is explainable from the recorded run statistics. The system SHALL NOT drop an
unexecutable target silently.

#### Scenario: A target too small for one share is recorded

- **WHEN** a target position cannot fund even one whole share (or the minimum crypto
  notional) and is therefore not traded
- **THEN** the system SHALL record that target as not executed with a reason indicating it
  was too small to fund the minimum tradable amount, rather than omitting it from the run's
  recorded outcomes

#### Scenario: An unpriceable target is recorded

- **WHEN** a target position cannot be priced by the broker
- **THEN** the system SHALL record that target as not executed with a reason indicating no
  price was available

### Requirement: Exclude known-unexecutable tickers from rebalance candidates

When assembling the candidate universe offered to the agent for a rebalance, the system
SHALL exclude tickers that are known to be unexecutable on the configured brokerage — for
example a listing the broker cannot price or trade — so that such a ticker is not
repeatedly re-selected as a target on every run. This exclusion applies to rebalance
candidate assembly and SHALL NOT change which already-held positions a rebalance may sell
or exit.

#### Scenario: A known-unexecutable ticker is not offered as a candidate

- **WHEN** a rebalance assembles the candidate universe for the agent and a ticker is known
  to be unexecutable on the configured brokerage
- **THEN** the system SHALL omit that ticker from the candidates offered to the agent, so it
  is not re-targeted every run

#### Scenario: Held positions are still actionable

- **WHEN** a ticker excluded from the rebalance candidates is already held by the session
- **THEN** the exclusion SHALL NOT prevent the rebalance from selling or exiting that held
  position
