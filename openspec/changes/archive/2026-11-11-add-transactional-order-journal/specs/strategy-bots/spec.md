## ADDED Requirements

### Requirement: Per-bot isolation in the tick

The tick SHALL process each active strategy bot (and each stopped bot being flattened)
independently: the trades, positions, cash and value records produced for one bot SHALL be
committed once that bot has been processed, before the next bot is processed. An error while
processing one bot — including the broker rejecting or refusing one of its orders — SHALL be
logged and SHALL NOT fail the tick, discard another bot's records, or prevent the remaining bots
from being processed. Orders a failed bot already submitted SHALL remain recoverable through
order reconciliation. The tick SHALL report the number of bots that failed alongside those
processed and skipped.

#### Scenario: One bot's broker rejection does not stop the others

- **WHEN** the broker rejects an order of one bot during a tick
- **THEN** the remaining bots SHALL still be processed and their trades recorded, and the tick
  SHALL complete successfully reporting one failed bot

#### Scenario: Earlier bots' records survive a later failure

- **WHEN** a bot fails after earlier bots in the same tick traded
- **THEN** the earlier bots' trades and positions SHALL remain recorded

#### Scenario: Stopped-bot flattening survives a later failure

- **WHEN** a stopped bot's position is sold during a tick and a later bot fails
- **THEN** the sale SHALL remain recorded and the position SHALL NOT be sold again on the next
  tick

### Requirement: No trading on a symbol with an unresolved order

Before deciding a bot's entries and exits, the tick SHALL reconcile unresolved orders. A bot that
still has an unresolved order for a symbol (an order recorded but not yet booked or closed out)
SHALL NOT submit another order for that symbol in that tick.

#### Scenario: Unresolved order blocks a repeat

- **WHEN** a bot's earlier sell of a symbol is still unresolved at the start of a tick
- **THEN** the bot SHALL NOT submit another order for that symbol in that tick

### Requirement: Bot sells never exceed the account's holdings

A strategy bot's exit or flattening sell SHALL be refused, sending no order, when the broker
account holds fewer shares of the symbol than the sell quantity. A refused sell SHALL leave the
bot's position unchanged and SHALL be logged; it SHALL NOT fail the tick.

#### Scenario: Flattening a position the account no longer holds

- **WHEN** a stopped bot records 4 shares of a symbol but the account holds none
- **THEN** no sell SHALL be sent, the position SHALL remain recorded, and the tick SHALL
  continue
