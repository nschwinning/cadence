## ADDED Requirements

### Requirement: Restore Cadence-tracked positions

The system SHALL provide an action that buys back, for one requested symbol or for every eligible
symbol, the quantity by which the account holds less than Cadence tracks — a shortfall or a
short position — so that the account again holds exactly the quantity Cadence tracks. At
execution time the system SHALL recompute the positions comparison from live broker data and
current Cadence records and SHALL act only on the recomputed missing quantity; it SHALL NOT accept
a caller-supplied quantity. It SHALL skip, with a reason, any symbol that is no longer short of
Cadence's quantity, has an open order, or is an equity while the equity market is closed. A broker
rejection for one symbol SHALL be reported for that symbol and SHALL NOT prevent the others. Restore
purchases SHALL go through the order journal as administrator orders and SHALL NOT be booked into
any AI-portfolio ledger, bot ledger, trade history or orchestrator pool.

#### Scenario: Short position restored to Cadence's quantity

- **WHEN** Cadence tracks 4 shares of a symbol, the account is short 6, and the operator restores
  it while the market is open
- **THEN** the system SHALL buy 10 shares and report it as bought

#### Scenario: Shortfall restored

- **WHEN** Cadence tracks 10 shares and the account holds 6
- **THEN** a restore SHALL buy 4 shares

#### Scenario: Matched or orphan symbol is not restored

- **WHEN** a restore is requested for a symbol whose account quantity is at least Cadence's
- **THEN** no order SHALL be sent and it SHALL be reported as skipped

#### Scenario: Restore leaves Cadence's books untouched

- **WHEN** a restore purchase fills
- **THEN** no AI-portfolio ledger, bot position, trade history or orchestrator capital SHALL
  change

### Requirement: Unresolved orders view

The account overview SHALL list every journaled order that is not yet booked or closed out, with
its owner, symbol, side, quantity, status and age, and the system SHALL provide an on-demand
action that runs order reconciliation and reports how many records were booked, closed out, or
left unresolved.

#### Scenario: Unbooked order is listed

- **WHEN** a journaled order has not been booked or closed out
- **THEN** the overview SHALL list it with its owner, symbol, side, quantity, status and age

#### Scenario: Reconcile on demand

- **WHEN** the operator requests reconciliation
- **THEN** the system SHALL reconcile unresolved orders and report the booked, closed-out and
  remaining counts

## MODIFIED Requirements

### Requirement: Committed-cash check

The account overview SHALL include a cash check comparing the cash Cadence believes is
committed against the account's cash. Committed cash SHALL be the sum of: each active AI
portfolio's cash (its allocated capital plus realised profit/loss, minus fees, minus the cost
basis of its open ledger positions); each active strategy bot's cash; each active bot
orchestrator's free capital; and the cash of each stopped orchestrator-deployed bot whose cash
has not yet been returned to its orchestrator; stopped manually created bots SHALL NOT count.
The account's cash used for the comparison SHALL exclude the proceeds of short sales (the
account's reported cash minus the absolute market value of its short positions), so short
positions never make the account appear to hold more free cash than it does; the overview SHALL
also show the reported cash and the short-sale proceeds it excludes.
The check SHALL list each contributor with its
name, kind and amount, the committed total, the account's cash, and the difference (account
cash minus committed total). When the difference is negative the check SHALL be flagged as a
shortfall. Computing the check SHALL NOT change any session, bot or orchestrator.

#### Scenario: Account covers Cadence's commitments

- **WHEN** the account's cash is at least the committed total
- **THEN** the check SHALL report a non-negative difference and no shortfall

#### Scenario: Cadence has committed more cash than the account holds

- **WHEN** the committed total exceeds the account's cash
- **THEN** the check SHALL report the negative difference and flag a shortfall

#### Scenario: Contributors are itemised

- **WHEN** the operator views the cash check
- **THEN** each active AI portfolio, active bot, active orchestrator and unreturned stopped
  orchestrator bot SHALL appear as its own line with its name, kind and cash amount

#### Scenario: Short-sale proceeds are excluded

- **WHEN** the account reports $294,000 cash while holding short positions worth $201,000
- **THEN** the check SHALL compare against $93,000 of cash and show the $201,000 excluded
