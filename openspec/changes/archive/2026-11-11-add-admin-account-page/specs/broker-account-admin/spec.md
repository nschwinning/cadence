## Purpose

Give the operator a live view of the shared broker account that every Cadence AI portfolio,
strategy bot and bot orchestrator trades in, reconcile it against what Cadence believes it holds
and has committed, and let the operator sell positions that no Cadence session owns.

## ADDED Requirements

### Requirement: Broker account overview

The system SHALL provide a read-only account overview, fetched live from the broker on each
request, containing the account's cash, buying power and total portfolio value. Every monetary
figure SHALL be in the account currency. When the broker cannot be reached or rejects the
request, the overview SHALL report the broker as unavailable with a non-secret reason rather
than failing silently or returning stale figures; no API key or secret SHALL ever be included
in the response.

#### Scenario: Overview shows live account figures

- **WHEN** the operator requests the account overview and the broker is reachable
- **THEN** the response SHALL include the account's current cash, buying power and total
  portfolio value as reported by the broker

#### Scenario: Broker unavailable

- **WHEN** the operator requests the account overview and the broker cannot be reached
- **THEN** the response SHALL mark the broker as unavailable with a non-secret reason and
  SHALL contain no account figures, positions or orders

### Requirement: Committed-cash check

The account overview SHALL include a cash check comparing the cash Cadence believes is
committed against the account's cash. Committed cash SHALL be the sum of: each active AI
portfolio's cash (its allocated capital plus realised profit/loss, minus fees, minus the cost
basis of its open ledger positions); each active strategy bot's cash; each active bot
orchestrator's free capital; and the cash of each stopped orchestrator-deployed bot whose cash
has not yet been returned to its orchestrator; stopped manually created bots SHALL NOT count.
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

### Requirement: Open orders listing

The account overview SHALL list the account's open orders with, for each, its symbol, side,
quantity, order type, status and submission time.

#### Scenario: Open orders are listed

- **WHEN** the account has open orders
- **THEN** the overview SHALL list each with its symbol, side, quantity, type, status and
  submission time

#### Scenario: No open orders

- **WHEN** the account has no open orders
- **THEN** the overview SHALL return an empty open-orders list

### Requirement: Positions comparison with orphan detection

The account overview SHALL compare, per symbol, the quantity the broker account holds against
the quantity Cadence tracks. The Cadence-tracked quantity SHALL be the sum over every AI
portfolio's open ledger positions (regardless of the portfolio's status) and every strategy
bot's open positions (regardless of the bot's status, so stopped bots not yet flattened still
count). Symbols SHALL be matched in the broker's symbol format so that, for example, a class
share or a crypto pair held under different spellings is treated as one symbol. Each row SHALL
carry the broker quantity, the Cadence quantity, and a classification:

- **matched** — the quantities agree within a small tolerance;
- **orphan** — the broker holds more than Cadence tracks; the **orphan quantity** is the
  excess (broker − Cadence);
- **shortfall** — Cadence tracks more than the broker holds;
- **short** — the broker holds a negative quantity.

A row whose symbol has an open order SHALL be marked as having a pending order. Only orphan
rows without a pending order SHALL be flattenable.

#### Scenario: Symbol owned entirely outside Cadence

- **WHEN** the broker holds 10 shares of a symbol Cadence does not track at all
- **THEN** the row SHALL be classified orphan with an orphan quantity of 10

#### Scenario: Symbol shared with Cadence

- **WHEN** the broker holds 15 shares of a symbol and Cadence sessions and bots together
  track 10
- **THEN** the row SHALL be classified orphan with an orphan quantity of 5

#### Scenario: Stopped bot positions still count as Cadence's

- **WHEN** a stopped bot still holds 4 shares of a symbol awaiting flattening and the broker
  holds 4 shares
- **THEN** the row SHALL be classified matched, not orphan

#### Scenario: Cadence tracks more than the account holds

- **WHEN** Cadence tracks 10 shares of a symbol but the broker holds 6
- **THEN** the row SHALL be classified shortfall and SHALL NOT be flattenable

#### Scenario: Symbol with a pending order is not flattenable

- **WHEN** an orphan row's symbol has an open order in the account
- **THEN** the row SHALL be marked as having a pending order and SHALL NOT be flattenable

### Requirement: Flatten orphan positions

The system SHALL provide an action that sells orphan quantities, either for one requested
symbol or for all flattenable orphan rows. At execution time the system SHALL recompute the
positions comparison from live broker data and current Cadence records, and SHALL act only on
the recomputed orphan quantities — it SHALL NOT accept or use a quantity supplied by the
caller. For each symbol it SHALL submit a market sell of exactly the recomputed orphan
quantity, so Cadence-tracked quantity is never sold. It SHALL skip, with a reason, any symbol
that is no longer an orphan, has an open order, is a shortfall or short position, or is an
equity while the equity market is closed (crypto orphans MAY be sold at any time). A broker
rejection for one symbol SHALL be reported for that symbol and SHALL NOT prevent the other
symbols from being processed. Orphan sells SHALL NOT be recorded in any AI-portfolio ledger,
bot ledger, trade history or orchestrator pool. The response SHALL report, per symbol, the
outcome (sold with quantity and order id, skipped with reason, or failed with the broker's
reason).

#### Scenario: Flatten a single orphan

- **WHEN** the operator flattens a symbol whose recomputed orphan quantity is 5 while the
  market is open
- **THEN** the system SHALL submit a market sell for 5 of that symbol and report it as sold

#### Scenario: Caller quantities are ignored

- **WHEN** a flatten request is made for a symbol whose orphan quantity has changed since the
  page was loaded
- **THEN** the system SHALL sell only the freshly recomputed orphan quantity

#### Scenario: Symbol no longer orphaned

- **WHEN** the operator flattens a symbol that is now matched
- **THEN** the system SHALL submit no order and report it as skipped

#### Scenario: Equity orphan while the market is closed

- **WHEN** the operator flattens an equity orphan while the equity market is closed
- **THEN** the system SHALL submit no order and report it as skipped because the market is
  closed

#### Scenario: Flatten all continues past a rejection

- **WHEN** the operator flattens all orphans and the broker rejects the sell for one symbol
- **THEN** that symbol SHALL be reported as failed with the broker's reason and every other
  flattenable orphan SHALL still be processed

#### Scenario: Orphan sells leave Cadence's books untouched

- **WHEN** an orphan quantity is sold
- **THEN** no AI-portfolio ledger, bot position, trade history or orchestrator capital SHALL
  change
