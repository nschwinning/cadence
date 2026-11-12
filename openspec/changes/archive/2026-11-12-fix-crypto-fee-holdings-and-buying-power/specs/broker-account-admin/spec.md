## ADDED Requirements

### Requirement: Write off crypto fee differences

The system SHALL provide an action that, for one requested crypto symbol or for every eligible
one, lowers the AI portfolios' ledger quantities to the quantity the broker account holds when
Cadence tracks more of that coin than the account holds by no more than 1% of Cadence's quantity
(the residue of fees the broker charged in the coin). The reduction SHALL be split across the AI
portfolios holding the coin in proportion to their ledger quantities, SHALL keep each ledger's
average cost, and SHALL send no order. It SHALL be recomputed at execution from live data and
SHALL NOT accept a caller-supplied quantity. Symbols that are equities, have an open order, are
not a shortfall, or exceed the 1% tolerance SHALL be skipped with a reason. The positions
comparison SHALL mark eligible rows as write-off candidates with the quantity that would be
written off.

#### Scenario: Fee residue is written off

- **WHEN** two AI portfolios hold 600 and 400 ADA in their ledgers and the account holds 997.5
- **THEN** a write-off SHALL lower them to 598.5 and 399 ADA at unchanged average cost, and send
  no order

#### Scenario: Larger gaps are not written off

- **WHEN** Cadence tracks 10 SOL and the account holds 9.5
- **THEN** the write-off SHALL skip SOL as beyond the 1% tolerance

### Requirement: Broker minimum in administrator actions

Restore and Flatten SHALL skip a crypto order worth less than $10 (the broker's minimum crypto
order value), estimated from the position's current price, with the reason "below the $10
minimum", sending no order.

#### Scenario: Tiny crypto restore is skipped

- **WHEN** a restore would buy 0.0226 SOL worth about $3
- **THEN** no order SHALL be sent and SOL SHALL be reported as skipped below the $10 minimum

## MODIFIED Requirements

### Requirement: Broker account overview

The system SHALL provide a read-only account overview, fetched live from the broker on each
request, containing the account's cash, its **cash buying power** (what can be bought without
margin, as the broker reports it), its **margin buying power**, and its total portfolio value. Every monetary
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

#### Scenario: Cash and margin buying power are reported separately

- **WHEN** the broker reports $57,899 of cash buying power and $325,946 of margin buying power
- **THEN** the overview SHALL report both figures, labelled as cash and margin buying power

