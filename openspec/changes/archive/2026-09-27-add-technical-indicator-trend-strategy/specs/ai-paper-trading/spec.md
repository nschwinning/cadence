## MODIFIED Requirements

### Requirement: Build an AI portfolio and execute it as paper trades

The system SHALL accept a request to build an AI portfolio over the current asset universe and an amount of capital to allocate, with options for risk profile, whether the portfolio is enrolled in daily rebalancing, an **asset scope** selecting which asset types the portfolio may hold: stocks only, crypto only, or both, and an optional **benchmark index** (from the fixed benchmark catalog) the session's performance is compared against. The asset scope SHALL default to both (the whole supported universe) when not specified, the allocated capital SHALL default to a configured default amount, and the benchmark SHALL default to a configured default benchmark (S&P 500) when not specified. A benchmark selection outside the catalog SHALL be rejected. The request SHALL NOT accept a candidate ticker list or per-position allocation caps. The AI SHALL be given as candidates every asset in the universe **whose category is within the selected asset scope** (enriched with name, sector, category, and eligibility) **and whose latest stored technical-indicator snapshot passes the deterministic uptrend trend gate**; a candidate whose gate does not pass, or that has no stored snapshot, SHALL be dropped from the candidate set and SHALL NOT be presented to the AI, so that a portfolio is only ever initialised with assets in a confirmed uptrend. The surviving candidates SHALL be annotated with their trend indicators. The AI MAY research and propose assets not currently in the universe (discovery is always enabled), and SHALL produce long-only target holdings whose allocations are fractions in [0, 1] that sum to approximately 1.0 (an allocation of ~0 excludes a holding). Newly discovered tickers SHALL be added to the universe on a best-effort basis, bounded by a configured maximum number of new assets per run, **and a discovered asset whose category falls outside the selected asset scope SHALL be rejected — not added and not traded**, and a discovered asset that does not pass the trend gate SHALL likewise be excluded from the candidate set; if an in-scope add fails the ticker SHALL still be eligible for the portfolio. The selected asset scope SHALL be persisted with the session so that later automated rebalances honour the same scope. The selected benchmark SHALL be persisted with the session so the session can be compared against that benchmark over its lifetime. The request SHALL be processed in the background and SHALL return immediately with an event identifier for polling. Execution SHALL: ask the AI for target holdings and allocations, create a portfolio **with a generated distinct name** and a paper-trading session, size each position from the allocated capital and a current quote, submit the corresponding buy orders through the brokerage, and record each executed trade and a run summary. The generated portfolio name SHALL be human-friendly and SHALL be distinct from the names of existing portfolios, so that portfolios and their sessions can be told apart; the name MAY reflect the selected risk profile. The AI's research SHALL be cost-bounded per run by a configured maximum number of reasoning turns and a hard cap on the number of web searches.

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

#### Scenario: Trend gate restricts the candidate universe

- **WHEN** a build assembles the candidate universe
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

## ADDED Requirements

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

The system SHALL persist, per AI build or rebalance run, the trend-decision context that shaped the candidates and holdings presented to the AI: the candidates that were **dropped by the trend gate** — each with its ticker and the reason it failed (which gate condition, or that it had no stored snapshot) — and the **indicator annotations handed to the AI** for the surviving candidates and for the current holdings (the indicator values and, for holdings, the reversal flags). This context SHALL be recorded on the AI-portfolio event alongside the run's reasoning and research transcript, and SHALL be captured best-effort so that a run which fails after the candidate/holdings assembly still persists the context gathered before the failure. A build run (which has no prior holdings) SHALL record the dropped candidates and the surviving-candidate annotations, with an empty holdings section. When a run performed no gating (for example a session frozen to a pre-trend prompt version), the trend-decision context SHALL be absent (null) rather than fabricated.

The system SHALL include the persisted trend-decision context in the run detail returned for a single AI run, so a client can show what was filtered out and what was handed to the AI.

#### Scenario: Build records its trend-decision context

- **WHEN** an AI build assembles its candidate universe under the trend gate
- **THEN** the recorded build event SHALL persist the candidates dropped by the gate (each with its reason) and the indicator annotations for the surviving candidates

#### Scenario: Rebalance records candidates and holdings context

- **WHEN** an AI rebalance assembles candidates and holdings
- **THEN** the recorded rebalance event SHALL persist the dropped candidates with reasons, the surviving-candidate indicator annotations, and each holding's indicator values and reversal flags

#### Scenario: Context captured despite a mid-run failure

- **WHEN** an AI run fails after candidate/holdings assembly but before completion
- **THEN** the recorded (failed) event SHALL still persist the trend-decision context gathered before the failure

#### Scenario: Run detail returns the trend-decision context

- **WHEN** a client requests a single AI run's detail
- **THEN** the returned detail SHALL include the run's persisted trend-decision context (dropped candidates with reasons and the indicator annotations handed to the AI), or absent when the run recorded none
