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

The system SHALL accept a request to build an AI portfolio over the entire current asset universe and an amount of capital to allocate, with options for risk profile and whether the portfolio is enrolled in daily rebalancing. The request SHALL NOT accept a candidate ticker list or per-position allocation caps. The AI SHALL be given every asset in the universe (enriched with name, sector, category, and eligibility) as candidates, MAY research and propose assets not currently in the universe (discovery is always enabled), and SHALL produce long-only target holdings whose allocations are fractions in [0, 1] that sum to approximately 1.0 (an allocation of ~0 excludes a holding). Newly discovered tickers SHALL be added to the universe on a best-effort basis, bounded by a configured maximum number of new assets per run; if an add fails the ticker SHALL still be eligible for the portfolio. The request SHALL be processed in the background and SHALL return immediately with an event identifier for polling. Execution SHALL: ask the AI for target holdings and allocations, create a portfolio and a paper-trading session, size each position from the allocated capital and a current quote, submit the corresponding buy orders through the brokerage, and record each executed trade and a run summary. The AI's research SHALL be cost-bounded per run by a configured maximum number of reasoning turns and a hard cap on the number of web searches.

#### Scenario: Queue a build

- **WHEN** a client requests an AI portfolio build while the asset universe is non-empty
- **THEN** the system SHALL create a build event, start background processing, and respond with the event id and a running status

#### Scenario: Empty universe rejected

- **WHEN** a client requests an AI portfolio build while the asset universe is empty
- **THEN** the system SHALL reject the request rather than starting a build

#### Scenario: Build executes

- **WHEN** the background build runs
- **THEN** the system SHALL create the portfolio and session, place the sized buy orders via the brokerage, record the executed trades and a run entry, and mark the build event succeeded (or partial if some orders could not be placed)

#### Scenario: AI discovers a new asset

- **WHEN** the AI proposes a holding whose ticker is not in the current universe
- **THEN** the system SHALL attempt to add that asset to the universe (up to the configured per-run limit) and SHALL still include the ticker in the portfolio and its trades even if the add fails

#### Scenario: Position too small to trade

- **WHEN** an allocation buys less than one whole share at the current quote
- **THEN** the system SHALL skip that position without failing the whole build and SHALL record it as not executed

### Requirement: Poll AI portfolio build status

The system SHALL let a client fetch the status of a build event by its identifier, exposing the run status, the resulting session and portfolio identifiers, the AI's structured output, the actions taken, any error, and a duration.

#### Scenario: Poll a build event

- **WHEN** a client polls a build event id
- **THEN** the system SHALL return the current status and, once finished, the session id, portfolio id, and the actions taken

### Requirement: Record sessions, trades, runs, and closed positions

The system SHALL persist, per paper-trading session, the executed trades (ticker, side, quantity, price, notional, signal type, order identity and status), a run entry per execution (counts and a trigger and status), and closed positions with realized profit and loss when positions are exited. Each AI build or rebalance SHALL be recorded as an AI-portfolio event capturing the AI's output (its reasoning) and the actions taken, and SHALL also persist the run's research transcript: the web searches performed during the run and, for each, the query and the results the agent received (or a note when a search was not performed, e.g. the per-run search budget was exhausted). Each trade and each closed position produced by an AI build or rebalance SHALL record a reference to the AI-portfolio event that produced it; trades not produced by an AI run SHALL leave this reference empty.

#### Scenario: Trades and run recorded on execution

- **WHEN** a build or rebalance places orders
- **THEN** the system SHALL record a trade per executed order, a run entry summarizing the execution, and (for exits) closed positions with realized P&L

#### Scenario: Trades and closed positions reference their run

- **WHEN** an AI build or rebalance records a trade or a closed position
- **THEN** the recorded trade or closed position SHALL reference the AI-portfolio event that produced it

#### Scenario: Research transcript persisted

- **WHEN** an AI build or rebalance reaches the agent and the agent performs web searches
- **THEN** the recorded AI-portfolio event SHALL persist each search's query and the results the agent received

#### Scenario: Research captured despite a mid-run failure

- **WHEN** an AI run fails after the agent has already performed one or more web searches
- **THEN** the recorded (failed) AI-portfolio event SHALL still persist the research captured before the failure

### Requirement: Read paper-trading session data

The system SHALL let a client list paper-trading sessions and read a session's trades, runs, positions, and its AI-portfolio events. An AI-portfolio event returned to a client SHALL include the AI's reasoning output and its persisted research transcript. A trade or closed position returned to a client SHALL include the reference to the AI-portfolio event that produced it, when present.

#### Scenario: Inspect a session

- **WHEN** a client requests a session's trades, runs, positions, or events
- **THEN** the system SHALL return the recorded data for that session

#### Scenario: Event includes reasoning and research

- **WHEN** a client reads an AI-portfolio event
- **THEN** the returned event SHALL include the AI reasoning output and the persisted research transcript

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
