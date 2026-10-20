## MODIFIED Requirements

### Requirement: Build an AI portfolio and execute it as paper trades

The system SHALL accept a request to build an AI portfolio over the current asset universe and an amount of capital to allocate, with options for risk profile, whether the portfolio is enrolled in daily rebalancing, an **asset scope** selecting which asset types the portfolio may hold: stocks only, crypto only, or both, whether the portfolio **uses the technical-indicator trend strategy** (an opt-in that defaults to off when not specified), whether the portfolio **enables an automatic hard stop-loss** (an opt-in that defaults to off when not specified) together with a **stop-loss threshold percentage** (defaulting to a configured default when the stop-loss is enabled without an explicit threshold), whether the portfolio **enables portfolio risk guardrails** (an opt-in that defaults to off when not specified) together with the guardrail parameters — a **maximum percentage per asset**, a **maximum percentage per asset class**, a **minimum number of positions**, and a **maximum invested percentage** (cash buffer) — each defaulting to a configured default when the guardrails are enabled without an explicit value, and an optional **benchmark index** (from the fixed benchmark catalog) the session's performance is compared against. The asset scope SHALL default to both (the whole supported universe) when not specified, the allocated capital SHALL default to a configured default amount, and the benchmark SHALL default to a configured default benchmark (S&P 500) when not specified. A benchmark selection outside the catalog SHALL be rejected. The request SHALL NOT accept a candidate ticker list. The request MAY carry the guardrail parameters described above; it SHALL NOT accept any other per-position allocation cap. The selected asset scope SHALL be persisted with the session so that later automated rebalances honour the same scope. The selected technical-indicator opt-in SHALL be persisted (frozen) with the session so that later automated rebalances apply the same choice; a session with no persisted opt-in (for example one built before this option existed) SHALL be treated as opted out. The selected stop-loss opt-in and, when enabled, its threshold percentage SHALL be persisted (frozen) with the session so the automatic stop-loss applies for the session's lifetime; a session with no persisted stop-loss setting (for example one built before this option existed) SHALL be treated as having the stop-loss disabled. The selected risk-guardrail opt-in and, when enabled, its parameters (maximum per asset, maximum per asset class, minimum number of positions, maximum invested percentage) SHALL be persisted (frozen) with the session so the same guardrails apply for the session's lifetime; a session with no persisted guardrail setting (for example one built before this option existed) SHALL be treated as having the guardrails disabled. The selected benchmark SHALL be persisted with the session so the session can be compared against that benchmark over its lifetime. The request SHALL be processed in the background and SHALL return immediately with an event identifier for polling.

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

#### Scenario: Stop-loss disabled by default

- **WHEN** a client requests a build without enabling the stop-loss
- **THEN** the system SHALL persist the session with the automatic stop-loss disabled

#### Scenario: Build persists the stop-loss setting

- **WHEN** a client requests a build enabling the stop-loss, optionally with a threshold percentage
- **THEN** the system SHALL persist the stop-loss as enabled on the created session, using the given threshold or the configured default when none is given

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

### Requirement: Poll AI portfolio build status

The system SHALL let a client fetch the status of a build event by its identifier, exposing the run status, the resulting session and portfolio identifiers, the AI's structured output, the actions taken, any error, and a duration. Because a build no longer allocates capital, the build event's actions represent the creation of the portfolio and session shell and the triggering of the opening allocation; the opening trades SHALL be recorded on the initial rebalance run (surfaced in the session's run history), not on the build event.

#### Scenario: Poll a build event

- **WHEN** a client polls a build event id
- **THEN** the system SHALL return the current status and, once finished, the session id, portfolio id, and the actions taken (the shell creation and the opening-allocation trigger)

#### Scenario: Opening trades recorded on the initial rebalance, not the build event

- **WHEN** a client polls a finished build and then inspects the session's run history
- **THEN** the opening trades SHALL appear on the session's initial rebalance run rather than on the build event's actions

## ADDED Requirements

### Requirement: Opening allocation runs through an initial rebalance

When a build has created the portfolio and the paper-trading session shell, the system SHALL produce the session's opening allocation by running one initial rebalance for the session through the standard rebalance path, triggered inline at creation. The initial rebalance SHALL run regardless of the session's schedule mode, so a manual (non-daily) session is allocated at creation and does not sit empty.

The initial rebalance SHALL be identical to any later rebalance for the session — it SHALL reason off the session's free cash, its open positions, and its total available value (realised and unrealised gains included). The only difference is that a freshly built session has no open positions yet, so its current value equals its allocated capital and there are no sells to place; there SHALL be no special-casing of the first allocation. All rebalance behaviors SHALL therefore apply to the opening allocation, including the trend gate, the company-fundamentals block, the risk-guardrail clamp, the reserved cash buffer, the unexecutable-weight redeploy, and the submit-sells-before-buys ordering.

A session enrolled in daily rebalancing SHALL additionally remain enrolled in the scheduled daily rebalance job. The readiness gate that defers a scheduled rebalance until a freshly built session's opening orders have settled SHALL track the orders of the initial rebalance (the opening allocation), not the order-less build event, so a scheduled rebalance never trades on unsettled opening holdings, and the session becomes eligible for the scheduled job once its opening allocation's orders have settled.

When the opening allocation cannot execute at creation (for example an all-equity session built while the equities market is closed), it SHALL record a skipped run and place no orders, and the allocation SHALL be produced at the next opportunity — the scheduled daily job for a daily-rebalancing session, the weekend crypto cadence for a crypto sleeve, or a later manual rebalance.

#### Scenario: Manual session is allocated at creation

- **WHEN** a build for a manual (non-daily-rebalancing) session finishes creating the shell while the market is open
- **THEN** the system SHALL trigger an initial rebalance that allocates the session's capital, so the session does not sit empty

#### Scenario: Daily session is allocated and stays enrolled

- **WHEN** a build for a daily-rebalancing session finishes creating the shell
- **THEN** the system SHALL trigger the initial rebalance for it AND leave the session enrolled in the scheduled daily rebalance job, eligible for the first scheduled run once its opening orders have settled

#### Scenario: Initial rebalance sizes with no open positions

- **WHEN** the initial rebalance runs for a freshly built session
- **THEN** it SHALL size the opening orders against the session's current value equal to its allocated capital, with no sells, exactly as a normal rebalance would for a session with no open positions

#### Scenario: Opening allocation applies rebalance-only enhancements

- **WHEN** the initial rebalance runs for a session that opted into a rebalance-only enhancement (for example company fundamentals or the trend strategy)
- **THEN** the opening allocation SHALL apply that enhancement, exactly as a later rebalance for the session would

#### Scenario: Readiness gate follows the opening allocation

- **WHEN** a scheduled rebalance job considers a freshly built session whose initial rebalance orders have not yet settled
- **THEN** the job SHALL defer the session until the initial rebalance's orders have settled, rather than treating the order-less build event as settled

#### Scenario: Market-closed opening allocation is deferred

- **WHEN** a freshly built all-equity session's opening allocation runs while the equities market is closed
- **THEN** it SHALL record a skipped run with no orders, and the allocation SHALL be produced at the next opportunity (the scheduled daily job, the weekend crypto cadence, or a later manual rebalance)
