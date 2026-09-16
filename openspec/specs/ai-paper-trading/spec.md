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

The system SHALL accept a request to build an AI portfolio over the current asset universe and an amount of capital to allocate, with options for risk profile, whether the portfolio is enrolled in daily rebalancing, and an **asset scope** selecting which asset types the portfolio may hold: stocks only, crypto only, or both. The asset scope SHALL default to both (the whole supported universe) when not specified, and the allocated capital SHALL default to a configured default amount. The request SHALL NOT accept a candidate ticker list or per-position allocation caps. The AI SHALL be given as candidates every asset in the universe **whose category is within the selected asset scope** (enriched with name, sector, category, and eligibility), MAY research and propose assets not currently in the universe (discovery is always enabled), and SHALL produce long-only target holdings whose allocations are fractions in [0, 1] that sum to approximately 1.0 (an allocation of ~0 excludes a holding). Newly discovered tickers SHALL be added to the universe on a best-effort basis, bounded by a configured maximum number of new assets per run, **and a discovered asset whose category falls outside the selected asset scope SHALL be rejected — not added and not traded**; if an in-scope add fails the ticker SHALL still be eligible for the portfolio. The selected asset scope SHALL be persisted with the session so that later automated rebalances honour the same scope. The request SHALL be processed in the background and SHALL return immediately with an event identifier for polling. Execution SHALL: ask the AI for target holdings and allocations, create a portfolio and a paper-trading session, size each position from the allocated capital and a current quote, submit the corresponding buy orders through the brokerage, and record each executed trade and a run summary. The AI's research SHALL be cost-bounded per run by a configured maximum number of reasoning turns and a hard cap on the number of web searches.

#### Scenario: Queue a build

- **WHEN** a client requests an AI portfolio build while the asset universe is non-empty
- **THEN** the system SHALL create a build event, start background processing, and respond with the event id and a running status

#### Scenario: Empty universe rejected

- **WHEN** a client requests an AI portfolio build while the asset universe is empty
- **THEN** the system SHALL reject the request rather than starting a build

#### Scenario: Build executes

- **WHEN** the background build runs
- **THEN** the system SHALL create the portfolio and session, place the sized buy orders via the brokerage, record the executed trades and a run entry, and mark the build event succeeded (or partial if some orders could not be placed)

#### Scenario: Default capital and scope

- **WHEN** a client requests a build without specifying allocated capital or asset scope
- **THEN** the system SHALL use the configured default capital amount and an asset scope of both (stocks and crypto)

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

### Requirement: Poll AI portfolio build status

The system SHALL let a client fetch the status of a build event by its identifier, exposing the run status, the resulting session and portfolio identifiers, the AI's structured output, the actions taken, any error, and a duration.

#### Scenario: Poll a build event

- **WHEN** a client polls a build event id
- **THEN** the system SHALL return the current status and, once finished, the session id, portfolio id, and the actions taken

### Requirement: Record sessions, trades, runs, and closed positions

The system SHALL persist, per paper-trading session, the executed trades (ticker, side, quantity, price, notional, signal type, order identity and status), a run entry per execution (counts and a trigger and status), the session's open positions in a ledger (per held ticker: quantity, weighted-average cost, and opened date), and closed positions with realized profit and loss when positions are exited. Every executed fill SHALL update the open-position ledger (a buy opens or increases an entry and re-computes its weighted-average cost; a sell reduces or removes it), and realized profit and loss SHALL be derived from the ledger entry's average cost and opened date. Each AI build or rebalance SHALL be recorded as an AI-portfolio event capturing the AI's output (its reasoning) and the actions taken, and SHALL also persist the run's research transcript: the web searches performed during the run and, for each, the query and the results the agent received (or a note when a search was not performed, e.g. the per-run search budget was exhausted). Each trade and each closed position produced by an AI build or rebalance SHALL record a reference to the AI-portfolio event that produced it; trades not produced by an AI run SHALL leave this reference empty.

#### Scenario: Trades and run recorded on execution

- **WHEN** a build or rebalance places orders
- **THEN** the system SHALL record a trade per executed order, a run entry summarizing the execution, updated open-position ledger entries, and (for exits) closed positions with realized P&L

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

The system SHALL let a client list paper-trading sessions and read a session's trades, runs, positions, its AI-portfolio events, and its daily portfolio-value snapshots. An AI-portfolio event returned to a client SHALL include the AI's reasoning output and its persisted research transcript. A trade or closed position returned to a client SHALL include the reference to the AI-portfolio event that produced it, when present. A session's value history SHALL be returned ordered oldest snapshot first.

#### Scenario: Inspect a session

- **WHEN** a client requests a session's trades, runs, positions, or events
- **THEN** the system SHALL return the recorded data for that session

#### Scenario: Event includes reasoning and research

- **WHEN** a client reads an AI-portfolio event
- **THEN** the returned event SHALL include the AI reasoning output and the persisted research transcript

#### Scenario: Read session value history

- **WHEN** a client requests a session's value history
- **THEN** the system SHALL return the session's daily value snapshots ordered oldest first, each with its date, total value, cash value, positions value, and day's profit and loss

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
total value and the day's profit and loss (absolute and percent), plus the single
best-performing and single worst-performing individual holding ranked by return
across all snapshotted sessions. A failure to deliver the report SHALL NOT fail the
snapshot job.

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
- **THEN** the system SHALL send a report with a per-session value and P&L line and
  with the best- and worst-performing individual holding across the snapshotted
  sessions

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

The system SHALL expose, on demand for a given paper-trading session, a summary of the session's live performance comprising: the current portfolio value (net asset value: cash plus open positions valued at current market quotes), cumulative realised profit/loss, live unrealised profit/loss on open positions, total return relative to the allocated capital (as both an absolute money amount and a fraction), and a risk-adjusted Sharpe ratio. Requesting the summary SHALL value the session's open positions against current quotes at request time (marking to market on load) rather than returning a stale stored valuation. A request for an unknown session SHALL fail as not found.

#### Scenario: Summary for a session with open positions

- **WHEN** a client requests the KPI summary for an existing session
- **THEN** the system SHALL mark the session's open positions to market and return the current portfolio value, realised P&L, unrealised P&L, total return relative to allocated capital, and the Sharpe ratio (or an unavailable Sharpe when history is insufficient)

#### Scenario: Unknown session

- **WHEN** a client requests the KPI summary for a session id that does not exist
- **THEN** the system SHALL respond with a not-found error and no summary

#### Scenario: Total return relative to allocated capital

- **WHEN** the KPI summary is computed
- **THEN** the total return SHALL be the current portfolio value measured against the session's allocated capital, provided both as an absolute money amount (current value minus allocated capital) and as a fraction of allocated capital

### Requirement: Sharpe ratio from the session's daily NAV series

The system SHALL compute a session's Sharpe ratio from the session's own ordered series of daily net-asset-value returns (the recorded daily value snapshots), as the mean daily return in excess of a configurable risk-free rate (defaulting to zero) divided by the standard deviation of daily returns, annualised by the square root of a configurable number of trading days per year. The Sharpe ratio SHALL be reported as unavailable (no value) when the session has fewer than a configured minimum number of daily returns, or when the daily returns have zero standard deviation. The computation SHALL rely solely on the session's recorded daily NAV series and SHALL NOT fetch external price history.

#### Scenario: Sufficient history

- **WHEN** a session has at least the configured minimum number of daily returns with non-zero variation
- **THEN** the system SHALL report a Sharpe ratio equal to the annualised mean-over-standard-deviation of those daily returns

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
