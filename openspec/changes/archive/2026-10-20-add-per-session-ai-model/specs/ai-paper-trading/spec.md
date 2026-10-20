## ADDED Requirements

### Requirement: AI model catalog

The system SHALL offer a fixed, server-defined catalog of selectable AI models that a paper-trading session's AI runs can execute on. Each catalog entry SHALL have a stable identifier used to reference it from a session and from a run, and a human-readable display name. A client SHALL be able to read the catalog so it can present the available models for selection. A session (and any AI run) SHALL reference a model only by a catalog identifier; a value outside the catalog SHALL be rejected. The catalog SHALL include the system's currently configured default model, which is the model used when a build does not select one.

#### Scenario: Read the model catalog

- **WHEN** a client requests the AI model catalog
- **THEN** the system SHALL return the catalog entries, each with its stable identifier and display name

#### Scenario: Catalog includes the configured default model

- **WHEN** a client reads the AI model catalog
- **THEN** the catalog SHALL include the system's configured default model as a selectable entry

### Requirement: AI runs execute on the session's frozen model

The system SHALL run a session's AI reasoning — both the opening allocation and every later rebalance — on the model frozen on the session at build time, rather than on a single global model. When a session has no usable frozen model (for example a legacy row somehow missing the value), the system SHALL fall back to the configured default model. The model a session runs on SHALL NOT change over the session's lifetime once frozen, so that a session's results are attributable to a single model.

#### Scenario: Rebalance uses the session's frozen model

- **WHEN** an opening allocation or a daily rebalance runs for a session whose frozen model differs from the configured default
- **THEN** the AI reasoning for that run SHALL execute on the session's frozen model, not the configured default

#### Scenario: Fallback when a session has no frozen model

- **WHEN** an AI run is triggered for a session whose frozen model is absent
- **THEN** the system SHALL execute the run on the configured default model rather than failing

## MODIFIED Requirements

### Requirement: Build an AI portfolio and execute it as paper trades

The system SHALL accept a request to build an AI portfolio over the current asset universe and an amount of capital to allocate, with options for risk profile, whether the portfolio is enrolled in daily rebalancing, an **asset scope** selecting which asset types the portfolio may hold: stocks only, crypto only, or both, whether the portfolio **uses the technical-indicator trend strategy** (an opt-in that defaults to off when not specified), whether the portfolio **uses company fundamentals** (an opt-in that defaults to off when not specified), whether the portfolio **enables an automatic hard stop-loss** (an opt-in that defaults to off when not specified) together with a **stop-loss threshold percentage** (defaulting to a configured default when the stop-loss is enabled without an explicit threshold), whether the portfolio **enables portfolio risk guardrails** (an opt-in that defaults to off when not specified) together with the guardrail parameters — a **maximum percentage per asset**, a **maximum percentage per asset class**, a **minimum number of positions**, and a **maximum invested percentage** (cash buffer) — each defaulting to a configured default when the guardrails are enabled without an explicit value, an optional **benchmark index** (from the fixed benchmark catalog) the session's performance is compared against, and an optional **AI model** (from the fixed model catalog) the session's AI runs execute on. The asset scope SHALL default to both (the whole supported universe) when not specified, the allocated capital SHALL default to a configured default amount, the benchmark SHALL default to a configured default benchmark (S&P 500) when not specified, and the model SHALL default to the configured default model when not specified. A benchmark selection outside the catalog SHALL be rejected. A model selection outside the model catalog SHALL be rejected. The request SHALL NOT accept a candidate ticker list. The request MAY carry the guardrail parameters described above; it SHALL NOT accept any other per-position allocation cap. The selected asset scope SHALL be persisted with the session so that later automated rebalances honour the same scope. The selected technical-indicator opt-in SHALL be persisted (frozen) with the session so that later automated rebalances apply the same choice; a session with no persisted opt-in (for example one built before this option existed) SHALL be treated as opted out. The selected company-fundamentals opt-in SHALL be persisted (frozen) with the session so that later automated rebalances apply the same choice; a session with no persisted fundamentals opt-in (for example one built before this option existed) SHALL be treated as opted out. The selected stop-loss opt-in and, when enabled, its threshold percentage SHALL be persisted (frozen) with the session so the automatic stop-loss applies for the session's lifetime; a session with no persisted stop-loss setting (for example one built before this option existed) SHALL be treated as having the stop-loss disabled. The selected risk-guardrail opt-in and, when enabled, its parameters (maximum per asset, maximum per asset class, minimum number of positions, maximum invested percentage) SHALL be persisted (frozen) with the session so the same guardrails apply for the session's lifetime; a session with no persisted guardrail setting (for example one built before this option existed) SHALL be treated as having the guardrails disabled. The selected benchmark SHALL be persisted with the session so the session can be compared against that benchmark over its lifetime. The selected model SHALL be persisted (frozen) with the session so every AI run for the session executes on that single model over its lifetime. The request SHALL be processed in the background and SHALL return immediately with an event identifier for polling.

Execution SHALL create a portfolio **with a generated distinct name** and a paper-trading session shell carrying the frozen options above, and SHALL place **no** opening orders directly. Instead it SHALL produce the session's opening allocation by triggering an initial rebalance for the new session through the standard rebalance path (see "Opening allocation runs through an initial rebalance"). The opening allocation SHALL therefore be governed by the rebalance requirements: assembling the candidate universe restricted to the session's asset scope; **when the session opts into the technical-indicator trend strategy**, restricting candidates to assets whose latest stored technical-indicator snapshot passes the deterministic uptrend trend gate (dropping those that fail or have no snapshot) and annotating the survivors with their trend indicators, so a portfolio is only ever initialised with assets in a confirmed uptrend, while **a session that does not opt in** has no trend gate applied and every in-scope candidate presented without indicator annotations; **when the session opted into company fundamentals**, attaching the fundamentals block; AI research and discovery of assets not currently in the universe (bounded by a configured per-run limit, rejecting a discovered asset whose category falls outside the selected asset scope); **when the guardrails are enabled, deterministically enforcing them on the target-weight vector before sizing** so that no single holding exceeds the maximum-per-asset cap, no asset class exceeds the maximum-per-class cap, and the total invested fraction does not exceed the maximum invested percentage (excess weight redistributed proportionally to holdings still below their caps, any shortfall held as cash) — the deterministic enforcement is the guarantee and the caps given to the AI are advisory only; reserving a cash buffer; redeploying unexecutable target weight across the executable targets; sizing each position against the session's current value (equal to the allocated capital when there are no open positions yet) and a current quote; submitting the buy orders through the brokerage; and recording each executed trade and a run summary. The minimum-number-of-positions guardrail SHALL NOT be enforced by fabricating holdings the AI did not pick: it is applied as an AI instruction plus the diversification floor implied by the maximum-per-asset cap, and when the AI returns fewer holdings than the configured minimum the shortfall SHALL be recorded as a guardrail observation on the run rather than causing the allocation to fail. The AI SHALL produce long-only target holdings whose allocations are fractions in [0, 1] that sum to approximately 1.0 (an allocation of ~0 excludes a holding). The generated portfolio name SHALL be human-friendly and SHALL be distinct from the names of existing portfolios, so that portfolios and their sessions can be told apart; the name MAY reflect the selected risk profile. The AI's research SHALL be cost-bounded per run by a configured maximum number of reasoning turns and a hard cap on the number of web searches.

#### Scenario: Queue a build

- **WHEN** a client requests an AI portfolio build while the asset universe is non-empty
- **THEN** the system SHALL create a build event, start background processing, and respond with the event id and a running status

#### Scenario: Empty universe rejected

- **WHEN** a client requests an AI portfolio build while the asset universe is empty
- **THEN** the system SHALL reject the request rather than starting a build

#### Scenario: Build executes

- **WHEN** the background build runs
- **THEN** the system SHALL create the portfolio and the paper-trading session shell, place no opening orders directly, trigger an initial rebalance that produces the opening trades and a run entry, and mark the build event succeeded (or failed with the reason)

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

#### Scenario: Default model

- **WHEN** a client requests a build without specifying a model
- **THEN** the system SHALL persist the configured default model as the session's frozen model

#### Scenario: Build persists a chosen model

- **WHEN** a client requests a build selecting a model from the model catalog
- **THEN** the system SHALL persist that model (frozen) with the created session so every AI run for the session uses it

#### Scenario: Build rejects an unknown model

- **WHEN** a client requests a build with a model identifier that is not in the model catalog
- **THEN** the system SHALL reject the request rather than starting a build

#### Scenario: Stop-loss disabled by default

- **WHEN** a client requests a build without enabling the stop-loss
- **THEN** the system SHALL persist the session with the automatic stop-loss disabled

#### Scenario: Build persists the stop-loss setting

- **WHEN** a client requests a build enabling the stop-loss, optionally with a threshold percentage
- **THEN** the system SHALL persist the stop-loss as enabled on the created session, using the given threshold or the configured default when none is given

#### Scenario: Fundamentals disabled by default

- **WHEN** a client requests a build without enabling company fundamentals
- **THEN** the system SHALL persist the session with company fundamentals disabled and its rebalances SHALL present no fundamentals block to the AI

#### Scenario: Build persists the fundamentals setting

- **WHEN** a client requests a build enabling company fundamentals
- **THEN** the system SHALL persist company fundamentals as enabled on the created session so later rebalances attach the fundamentals block when the session's frozen prompt version supports it

#### Scenario: Guardrails disabled by default

- **WHEN** a client requests a build without enabling the risk guardrails
- **THEN** the system SHALL persist the session with the risk guardrails disabled and SHALL apply no allocation caps during the opening allocation

#### Scenario: Build persists the guardrail settings

- **WHEN** a client requests a build enabling the risk guardrails, optionally with parameters
- **THEN** the system SHALL persist the guardrails as enabled on the created session, using the given maximum-per-asset, maximum-per-class, minimum-positions, and maximum-invested values or the configured defaults when any is not given

#### Scenario: Build clamps an over-cap holding

- **WHEN** a build with guardrails enabled has its opening allocation receive AI target allocations in which a single holding exceeds the maximum-per-asset cap
- **THEN** the system SHALL reduce that holding to the cap and redistribute the excess weight to the remaining holdings still below their caps before sizing the positions

#### Scenario: Build caps an over-concentrated asset class

- **WHEN** a build with guardrails enabled has its opening allocation receive AI target allocations whose combined weight in one asset class exceeds the maximum-per-class cap
- **THEN** the system SHALL reduce that class's combined weight to the cap and redistribute the excess to holdings in other classes still below their caps before sizing

#### Scenario: Build holds back a cash buffer

- **WHEN** a build with guardrails enabled has a maximum invested percentage below 100%
- **THEN** the opening allocation SHALL scale the target weights so the total invested does not exceed the maximum invested percentage and SHALL leave the remainder as cash

#### Scenario: Build records a minimum-positions shortfall without fabricating holdings

- **WHEN** a build with guardrails enabled has its opening allocation receive AI target allocations containing fewer holdings than the configured minimum number of positions
- **THEN** the system SHALL NOT invent additional holdings and SHALL record the shortfall as a guardrail observation on the run while completing the opening allocation with the AI's holdings (after clamping)

#### Scenario: Scope restricts the candidate universe

- **WHEN** a build requests an asset scope of stocks only (or crypto only)
- **THEN** the opening allocation SHALL be given only universe assets whose category matches the scope, and the resulting portfolio SHALL contain only assets of the selected type

#### Scenario: Build opts out of the trend strategy by default

- **WHEN** a client requests a build without specifying the technical-indicator opt-in
- **THEN** the system SHALL persist the session as opted out, and the opening allocation SHALL NOT apply the trend gate and SHALL present every in-scope candidate to the AI without indicator annotations

#### Scenario: Trend gate restricts the candidate universe

- **WHEN** a build that opted into the technical-indicator trend strategy has its opening allocation assemble the candidate universe
- **THEN** the system SHALL present to the AI only in-scope candidates whose latest indicator snapshot passes the uptrend gate (dropping those that fail or have no snapshot), so the initial portfolio only enters trend-confirmed assets

#### Scenario: AI discovers a new asset

- **WHEN** the AI proposes a holding whose ticker is not in the current universe and whose category is within the selected asset scope
- **THEN** the system SHALL attempt to add that asset to the universe (up to the configured per-run limit) and SHALL still include the ticker in the portfolio and its trades even if the add fails

#### Scenario: AI discovers an out-of-scope asset

- **WHEN** the AI proposes a holding whose category falls outside the selected asset scope
- **THEN** the system SHALL reject that asset — neither adding it to the universe nor trading it — while continuing the rest of the opening allocation

#### Scenario: Position too small to trade

- **WHEN** an allocation buys less than one whole share at the current quote
- **THEN** the system SHALL skip that position without failing the whole opening allocation and SHALL record it as not executed

### Requirement: Record sessions, trades, runs, and closed positions

The system SHALL persist, per paper-trading session, the executed trades (ticker, side, quantity, price, notional, signal type, order identity and status), a run entry per execution (counts and a trigger and status), the session's open positions in a ledger (per held ticker: quantity, weighted-average cost, and opened date), and closed positions with realized profit and loss when positions are exited. Every executed fill SHALL update the open-position ledger (a buy opens or increases an entry and re-computes its weighted-average cost; a sell reduces or removes it), and realized profit and loss SHALL be derived from the ledger entry's average cost and opened date. Each AI build or rebalance SHALL be recorded as an AI-portfolio event capturing the AI's output (its reasoning), the actions taken, and **the identifier of the AI model that produced the run**, and SHALL also persist the run's research transcript: the web searches performed during the run and, for each, the query and the results the agent received (or a note when a search was not performed, e.g. the per-run search budget was exhausted). Each trade, each closed position, and each run produced by an AI build or rebalance SHALL record a reference to the AI-portfolio event that produced it; trades, closed positions, and runs not produced by an AI build or rebalance — such as automatic stop-loss runs or scheduled/manual scanner runs — SHALL leave this reference empty.

#### Scenario: Trades and run recorded on execution

- **WHEN** a build or rebalance places orders
- **THEN** the system SHALL record a trade per executed order, a run entry summarizing the execution, updated open-position ledger entries, and (for exits) closed positions with realized P&L

#### Scenario: Trades and closed positions reference their run

- **WHEN** an AI build or rebalance records a trade or a closed position
- **THEN** the recorded trade or closed position SHALL reference the AI-portfolio event that produced it

#### Scenario: Runs reference their producing AI event

- **WHEN** an AI build or rebalance records a run entry
- **THEN** the recorded run SHALL reference the AI-portfolio event that produced it

#### Scenario: AI run records its model

- **WHEN** an AI build or rebalance records an AI-portfolio event
- **THEN** the recorded event SHALL capture the identifier of the model that produced the run

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

The system SHALL let a client list paper-trading sessions and read a session's trades, runs, positions, its AI-portfolio events, and its daily portfolio-value snapshots. A session returned to a client SHALL include the name of the portfolio it trades so the client can identify the session by portfolio; when the portfolio cannot be resolved the name SHALL be absent (null) rather than causing an error. A session returned to a client SHALL include the benchmark it is compared against. A session returned to a client SHALL include the identifier of the AI model it runs on. A session returned to a client SHALL include its asset scope — whether it trades stocks only, crypto only, or both. A session returned to a client SHALL include its stop-loss configuration: whether the automatic stop-loss is enabled and, when enabled, its threshold percentage. A session returned to a client SHALL include its company-fundamentals configuration: whether company fundamentals are enabled. A session returned to a client SHALL include its risk-guardrail configuration: whether the risk guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage. A session returned to a client SHALL include its contributed capital (the sum of its recorded capital contributions, equal to its allocated capital). An AI-portfolio event returned to a client SHALL include the AI's reasoning output and its persisted research transcript. A trade, closed position, or run returned to a client SHALL include the reference to the AI-portfolio event that produced it, when present. A session's value history SHALL be returned ordered oldest snapshot first, and each snapshot in the returned history SHALL carry the value of a buy-and-hold of the benchmark that receives the session's capital contributions on their effective dates — each contribution buying benchmark units at that date's benchmark price — so the benchmark line starts at the session's first contribution on the first snapshot date and steps up by each later contribution; for a session with a single contribution this is equivalent to a buy-and-hold of the allocated capital rebased to the first snapshot date. When the benchmark has no stored price on or before a snapshot's date, that snapshot's benchmark value SHALL be absent (null) rather than causing an error.

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

#### Scenario: Session reports its model

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include the identifier of the AI model it runs on

#### Scenario: Session reports its asset scope

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include its asset scope (stocks, crypto, or both), defaulting to both when no explicit scope was recorded

#### Scenario: Session reports its stop-loss configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its automatic stop-loss is enabled and, when enabled, its threshold percentage

#### Scenario: Session reports its fundamentals configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its company fundamentals are enabled, defaulting to disabled when no explicit setting was recorded

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

### Requirement: Browse AI run history and details

The system SHALL let a client list AI runs (build and rebalance events) across all sessions, ordered newest first, with pagination and optional filtering by run type and status, and SHALL return a total count for the applied filter. The system SHALL let a client open a single AI run by its identifier and receive that run's detail: the run's reasoning output and research transcript, the identifier of the AI model that produced the run, the trades it opened, and the positions it closed (the trades and closed positions referencing that run). Requesting an unknown run identifier SHALL return a not-found error.

#### Scenario: List runs across sessions

- **WHEN** a client requests the AI run list
- **THEN** the system SHALL return AI runs across all sessions ordered newest first, honoring pagination and any type/status filter, together with the matching total count

#### Scenario: Open a run's detail

- **WHEN** a client requests a run by its identifier
- **THEN** the system SHALL return the run's reasoning, its research transcript, the identifier of the model that produced it, the trades it opened, and the positions it closed

#### Scenario: Unknown run

- **WHEN** a client requests a run identifier that does not exist
- **THEN** the system SHALL return a not-found error
