## ADDED Requirements

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

## MODIFIED Requirements

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
