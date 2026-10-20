## ADDED Requirements

### Requirement: Rebalancing prompt includes company fundamentals

The system SHALL provide a **company-fundamentals** rebalance strategy as a
per-session **opt-in that defaults to off**, delivered as a new rebalance prompt
version (per the versioned-prompt requirement). When a session has opted into
fundamentals **and** is frozen on a prompt version at or after the
fundamentals-aware version, its rebalances SHALL supply the agent with a
per-ticker **company fundamentals** block attached to **both** the supplied buy
candidates and the current holdings, so the agent can weigh company financials
when deciding what to buy and when deciding whether to sell, trim, or hold. A
session that did not opt in, or that is frozen on a prompt version predating the
fundamentals-aware version, SHALL receive no fundamentals block and SHALL behave
exactly as it did before this change. The fundamentals-aware prompt version's
instructions SHALL describe the fundamentals object **defensively** — weighing it
when present and tolerating its absence — so that an opted-out session frozen on
that version reads correctly with no fundamentals attached.

For each asset that has usable fundamentals, the block SHALL carry only figures
derived from the asset's most recent stored annual financials, requiring no
additional data fetch at run time: **gross margin**, **operating margin**, and
**net margin** (each as a ratio of the corresponding income figure to revenue),
**diluted earnings per share** (falling back to basic EPS when diluted is absent),
and the absolute **revenue**, **net income**, and **operating cash flow** as scale
and profitability signals. The block SHALL NOT include price-derived ratios (such
as price-to-earnings), multi-period growth rates, or leverage / balance-sheet
metrics, because the stored data does not support them. A margin that cannot be
computed (for example, because revenue is zero or missing) SHALL be omitted rather
than reported as a misleading value.

When an asset has no usable fundamentals — a crypto asset, an asset with no stored
fundamentals record, or a record whose fetch did not produce usable data — the
block SHALL render an explicit **"fundamentals unavailable"** marker for that asset
rather than inventing figures or omitting the asset.

The prompt SHALL retain the existing rebalance constraints (long-only, target
weights sum to approximately 1.0, per-trade transaction-cost discipline, crypto
handled with around-the-clock tickers, discovery and web-search caps) and SHALL NOT
change the AI output schema — omitting a holding or giving it an allocation of ~0
still means sell/exit.

#### Scenario: Opted-in session on the fundamentals-aware prompt attaches the block

- **WHEN** a rebalance runs for a session that opted into fundamentals and is frozen on the fundamentals-aware prompt version (or later)
- **THEN** the agent SHALL be presented with a per-ticker fundamentals block on both the candidates and the current holdings

#### Scenario: Opted-out session receives no fundamentals block

- **WHEN** a rebalance runs for a session that did not opt into fundamentals, even if it is frozen on the fundamentals-aware prompt version
- **THEN** the agent SHALL be given the candidates and holdings without any fundamentals block

#### Scenario: Older sessions receive no fundamentals block

- **WHEN** a rebalance runs for a session frozen to a prompt version that predates the fundamentals-aware version
- **THEN** the agent SHALL be given the candidates and holdings without any fundamentals block, unchanged from that frozen version's behavior

#### Scenario: Fundamentals figures are derived from stored financials

- **WHEN** the fundamentals block is assembled for an asset whose stored financials include revenue and the corresponding income figures
- **THEN** that asset's fundamentals block SHALL report gross, operating, and net margins, diluted (or basic) EPS, and the absolute revenue, net income, and operating cash flow
- **AND** a margin whose revenue is zero or missing SHALL be omitted rather than reported as a misleading value

#### Scenario: Unavailable fundamentals are marked, not fabricated

- **WHEN** the fundamentals block is assembled for an asset that is crypto, has no stored fundamentals record, or has a record whose fetch produced no usable data
- **THEN** that asset SHALL be shown with a "fundamentals unavailable" marker and no invented figures

#### Scenario: Fundamentals-aware prompt preserves the output contract

- **WHEN** the fundamentals-aware rebalance prompt is used for a run
- **THEN** the agent SHALL still return long-only target allocations summing to approximately 1.0, with an omitted or ~0-weight holding meaning exit, unchanged from the prior prompt version's output schema

## MODIFIED Requirements

### Requirement: Build an AI portfolio and execute it as paper trades

The system SHALL accept a request to build an AI portfolio over the current asset universe and an amount of capital to allocate, with options for risk profile, whether the portfolio is enrolled in daily rebalancing, an **asset scope** selecting which asset types the portfolio may hold: stocks only, crypto only, or both, whether the portfolio **uses the technical-indicator trend strategy** (an opt-in that defaults to off when not specified), whether the portfolio **uses company fundamentals** (an opt-in that defaults to off when not specified), whether the portfolio **enables an automatic hard stop-loss** (an opt-in that defaults to off when not specified) together with a **stop-loss threshold percentage** (defaulting to a configured default when the stop-loss is enabled without an explicit threshold), whether the portfolio **enables portfolio risk guardrails** (an opt-in that defaults to off when not specified) together with the guardrail parameters — a **maximum percentage per asset**, a **maximum percentage per asset class**, a **minimum number of positions**, and a **maximum invested percentage** (cash buffer) — each defaulting to a configured default when the guardrails are enabled without an explicit value, and an optional **benchmark index** (from the fixed benchmark catalog) the session's performance is compared against. The asset scope SHALL default to both (the whole supported universe) when not specified, the allocated capital SHALL default to a configured default amount, and the benchmark SHALL default to a configured default benchmark (S&P 500) when not specified. A benchmark selection outside the catalog SHALL be rejected. The request SHALL NOT accept a candidate ticker list. The request MAY carry the guardrail parameters described above; it SHALL NOT accept any other per-position allocation cap. The AI SHALL be given as candidates every asset in the universe **whose category is within the selected asset scope** (enriched with name, sector, category, and eligibility). **When the session opts into the technical-indicator trend strategy**, the candidate set SHALL additionally be restricted to assets whose latest stored technical-indicator snapshot passes the deterministic uptrend trend gate — a candidate whose gate does not pass, or that has no stored snapshot, SHALL be dropped and SHALL NOT be presented to the AI, so that a portfolio is only ever initialised with assets in a confirmed uptrend — and the surviving candidates SHALL be annotated with their trend indicators. **When the session does not opt in, no trend gate SHALL be applied and every in-scope candidate SHALL be presented to the AI without indicator annotations.** The AI MAY research and propose assets not currently in the universe (discovery is always enabled), and SHALL produce long-only target holdings whose allocations are fractions in [0, 1] that sum to approximately 1.0 (an allocation of ~0 excludes a holding). Newly discovered tickers SHALL be added to the universe on a best-effort basis, bounded by a configured maximum number of new assets per run, **and a discovered asset whose category falls outside the selected asset scope SHALL be rejected — not added and not traded**, and — **only when the session opted into the trend strategy** — a discovered asset that does not pass the trend gate SHALL likewise be excluded from the candidate set; if an in-scope add fails the ticker SHALL still be eligible for the portfolio. **When the session opted into the risk guardrails, the AI SHALL additionally be told the guardrail caps (maximum per asset, maximum per asset class, minimum number of positions, and maximum invested percentage) so it can plan within them.** The selected asset scope SHALL be persisted with the session so that later automated rebalances honour the same scope. The selected technical-indicator opt-in SHALL be persisted (frozen) with the session so that later automated rebalances apply the same choice; a session with no persisted opt-in (for example one built before this option existed) SHALL be treated as opted out. The selected company-fundamentals opt-in SHALL be persisted (frozen) with the session so that later automated rebalances apply the same choice; a session with no persisted fundamentals opt-in (for example one built before this option existed) SHALL be treated as opted out. The selected stop-loss opt-in and, when enabled, its threshold percentage SHALL be persisted (frozen) with the session so the automatic stop-loss applies for the session's lifetime; a session with no persisted stop-loss setting (for example one built before this option existed) SHALL be treated as having the stop-loss disabled. The selected risk-guardrail opt-in and, when enabled, its parameters (maximum per asset, maximum per asset class, minimum number of positions, maximum invested percentage) SHALL be persisted (frozen) with the session so the same guardrails apply for the session's lifetime; a session with no persisted guardrail setting (for example one built before this option existed) SHALL be treated as having the guardrails disabled. The selected benchmark SHALL be persisted with the session so the session can be compared against that benchmark over its lifetime. The request SHALL be processed in the background and SHALL return immediately with an event identifier for polling. Execution SHALL: ask the AI for target holdings and allocations, create a portfolio **with a generated distinct name** and a paper-trading session, **when the guardrails are enabled deterministically enforce them on the target-weight vector before sizing** so that no single holding exceeds the maximum-per-asset cap, no asset class exceeds the maximum-per-class cap, and the total invested fraction does not exceed the maximum invested percentage (the remainder held as cash) — excess weight removed by a per-asset or per-class cap SHALL be redistributed proportionally to the holdings still below their caps, and when the caps cannot absorb the full capital the shortfall SHALL remain as cash — size each position from the allocated capital and a current quote, submit the corresponding buy orders through the brokerage, and record each executed trade and a run summary. The deterministic guardrail enforcement is the guarantee; the caps given to the AI are advisory only. The minimum-number-of-positions guardrail SHALL NOT be enforced by fabricating holdings the AI did not pick: it is applied as the AI instruction above plus the diversification floor implied by the maximum-per-asset cap, and when the AI returns fewer holdings than the configured minimum the shortfall SHALL be recorded as a guardrail observation on the run rather than causing the build to fail. The generated portfolio name SHALL be human-friendly and SHALL be distinct from the names of existing portfolios, so that portfolios and their sessions can be told apart; the name MAY reflect the selected risk profile. The AI's research SHALL be cost-bounded per run by a configured maximum number of reasoning turns and a hard cap on the number of web searches.

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

#### Scenario: Fundamentals disabled by default

- **WHEN** a client requests a build without enabling company fundamentals
- **THEN** the system SHALL persist the session with company fundamentals disabled and its rebalances SHALL present no fundamentals block to the AI

#### Scenario: Build persists the fundamentals setting

- **WHEN** a client requests a build enabling company fundamentals
- **THEN** the system SHALL persist company fundamentals as enabled on the created session so later rebalances attach the fundamentals block when the session's frozen prompt version supports it

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

### Requirement: Read paper-trading session data

The system SHALL let a client list paper-trading sessions and read a session's trades, runs, positions, its AI-portfolio events, and its daily portfolio-value snapshots. A session returned to a client SHALL include the name of the portfolio it trades so the client can identify the session by portfolio; when the portfolio cannot be resolved the name SHALL be absent (null) rather than causing an error. A session returned to a client SHALL include the benchmark it is compared against. A session returned to a client SHALL include its asset scope — whether it trades stocks only, crypto only, or both. A session returned to a client SHALL include its stop-loss configuration: whether the automatic stop-loss is enabled and, when enabled, its threshold percentage. A session returned to a client SHALL include its company-fundamentals configuration: whether company fundamentals are enabled. A session returned to a client SHALL include its risk-guardrail configuration: whether the risk guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage. A session returned to a client SHALL include its contributed capital (the sum of its recorded capital contributions, equal to its allocated capital). An AI-portfolio event returned to a client SHALL include the AI's reasoning output and its persisted research transcript. A trade, closed position, or run returned to a client SHALL include the reference to the AI-portfolio event that produced it, when present. A session's value history SHALL be returned ordered oldest snapshot first, and each snapshot in the returned history SHALL carry the value of a buy-and-hold of the benchmark that receives the session's capital contributions on their effective dates — each contribution buying benchmark units at that date's benchmark price — so the benchmark line starts at the session's first contribution on the first snapshot date and steps up by each later contribution; for a session with a single contribution this is equivalent to a buy-and-hold of the allocated capital rebased to the first snapshot date. When the benchmark has no stored price on or before a snapshot's date, that snapshot's benchmark value SHALL be absent (null) rather than causing an error.

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
