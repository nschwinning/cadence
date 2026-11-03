## MODIFIED Requirements

### Requirement: Strategy bot session lifecycle

The system SHALL let a client create a strategy-bot session bound to a single
strategy, a **set of one or more equity assets drawn from the shared asset universe**,
an initial capital amount that serves as the session's **shared capital budget**, a
benchmark, and the strategy's parameters. The client SHALL be able to choose the traded
set either as specific universe assets or as the **whole eligible universe**, in which
case the system SHALL resolve the currently eligible universe equities into the
session's traded set at creation. A session SHALL only ever trade assets that are
eligible equities in the universe; the system SHALL NOT create or admit any asset that
is not already in the universe. A bot session SHALL be persisted independently of AI
paper-trading sessions, with no foreign key to paper-trading sessions. A bot session
SHALL have a lifecycle status of active, stopped, or archived. The system SHALL let a
client stop an active session and archive a stopped session. Creating a bot session
SHALL NOT invoke any AI model.

#### Scenario: Create a bot session

- **WHEN** a client creates a bot session with a valid strategy key, a set of eligible
  universe assets, an initial capital budget, a benchmark, and valid strategy parameters
- **THEN** the system SHALL persist a new active bot session bound to that set of assets
  with the budget as its starting shared capital, and return it, without invoking any AI
  model

#### Scenario: Whole-universe selection resolves the eligible set

- **WHEN** a client creates a bot session selecting the whole universe
- **THEN** the system SHALL resolve the currently eligible universe equities into the
  session's traded set at creation and trade that set

#### Scenario: Reject an unknown strategy or non-universe asset

- **WHEN** a client creates a bot session with an unregistered strategy key, or with any
  asset that is not an eligible equity in the universe
- **THEN** the system SHALL reject the request rather than creating a session, and SHALL
  NOT create a new asset

#### Scenario: Stop and archive

- **WHEN** a client stops an active bot session and later archives it
- **THEN** the session SHALL transition active → stopped → archived and SHALL no
  longer be ticked once stopped

### Requirement: Strategy registry and MA Crossover strategy

The system SHALL maintain a registry mapping each strategy key to its
implementation, its parameter schema, the number of historical bars it
requires, and a human-readable **explanation** of what the strategy does. Each strategy
SHALL be a pure signal generator that, given recent bars, the current position, and
parameters, returns one of ENTER_LONG, EXIT, or HOLD together with a human-readable
reason, performing no I/O and holding no persisted state. The system SHALL provide an
**MA Crossover** strategy: when the fast simple moving average crosses above the slow
simple moving average it SHALL signal ENTER_LONG; when the fast average crosses back
below the slow average it SHALL signal EXIT; otherwise HOLD. With fewer bars than the
strategy requires it SHALL signal HOLD.

#### Scenario: Fast crosses above slow enters long

- **WHEN** the MA Crossover strategy evaluates bars where the fast SMA has just
  crossed above the slow SMA and no position is open
- **THEN** it SHALL return ENTER_LONG with a reason

#### Scenario: Fast crosses below slow exits

- **WHEN** the MA Crossover strategy evaluates bars where the fast SMA has just
  crossed below the slow SMA and a long position is open
- **THEN** it SHALL return EXIT with a reason

#### Scenario: Insufficient history holds

- **WHEN** the strategy is given fewer bars than its required history
- **THEN** it SHALL return HOLD rather than erroring

#### Scenario: Registry exposes required history and params

- **WHEN** the runner prepares to evaluate a strategy
- **THEN** the registry SHALL provide that strategy's required bar count and
  parameter schema so the runner can fetch enough bars and validate parameters

#### Scenario: Registry exposes a strategy explanation

- **WHEN** a client requests the strategy catalog
- **THEN** each strategy entry SHALL include a human-readable explanation of what the
  strategy does, suitable for display to the user

### Requirement: Cron-triggered tick with market-hours gating

The system SHALL expose a tick endpoint, guarded by the shared cron token, that
advances all active bot sessions. The endpoint SHALL be a no-op (processing no
sessions) when the equity market is closed per the broker clock. For each active
session the runner SHALL process **every asset in the session's traded set**: it SHALL
fetch each symbol's required history of bars at the configured signal bar timeframe,
recompute indicators fresh each tick, evaluate the strategy, and act on the signal.
Within a session the runner SHALL process **exits before entries** and SHALL iterate
candidate entries in a **deterministic order**, so that which symbols are entered when
capital or the maximum-concurrent-positions limit is constraining is deterministic and
reproducible. The bars the runner evaluates SHALL be obtained from the subsystem's
configured market-data source and SHALL satisfy the market-data freshness requirement,
so signals are computed on data current as of the tick. The runner SHALL hold no
in-memory state across ticks: only position state, the trade ledger, and value
snapshots are persisted. The tick interval and the signal bar timeframe SHALL be
configurable, defaulting to five minutes each.

#### Scenario: Reject an unauthenticated tick

- **WHEN** the tick endpoint is called without a valid cron token
- **THEN** the system SHALL reject the request and advance no sessions

#### Scenario: Market closed is a no-op

- **WHEN** the tick endpoint is called while the equity market is closed
- **THEN** the system SHALL process no sessions and record no trades

#### Scenario: Stateless recompute per tick

- **WHEN** the tick runner processes an active session
- **THEN** it SHALL fetch the required bar history for each traded symbol, recompute
  indicators from those bars, and evaluate the strategy without relying on state carried
  from a prior tick

#### Scenario: Exits processed before entries, entries deterministic

- **WHEN** the tick runner processes a session in which some open positions must exit and
  some symbols signal entry
- **THEN** it SHALL process all exits first (freeing capital to the shared pool) and then
  evaluate entries in a deterministic order, so capital- or limit-constrained entry
  selection is reproducible

#### Scenario: Only active sessions are ticked

- **WHEN** the tick runner runs while some sessions are stopped or archived
- **THEN** it SHALL advance only active sessions

### Requirement: Optional take-profit, stop-loss, and drawdown kill-switch

A bot session MAY configure an optional take-profit and an optional stop-loss as
percentage thresholds against each open position's entry price; when unset, neither
triggers. On each tick, for **every open position** the system SHALL exit that position
if its current price has risen to or above the take-profit threshold or fallen to or
below the stop-loss threshold, independently of the strategy signal. The system SHALL
also enforce a **whole-session** drawdown kill-switch: when a session's total value
falls by at least the configured drawdown limit from its peak, the system SHALL exit
**all** open positions and stop the session so it is no longer ticked.

#### Scenario: Take-profit exits

- **WHEN** an open position with a configured take-profit ticks at a price at or above
  the take-profit threshold
- **THEN** the system SHALL exit that position regardless of the strategy signal

#### Scenario: Stop-loss exits

- **WHEN** an open position with a configured stop-loss ticks at a price at or below the
  stop-loss threshold
- **THEN** the system SHALL exit that position regardless of the strategy signal

#### Scenario: Thresholds unset never trigger

- **WHEN** a session has no take-profit and no stop-loss configured
- **THEN** neither a take-profit nor a stop-loss exit SHALL occur for any position

#### Scenario: Drawdown kill-switch stops the session

- **WHEN** a session's total value has fallen by at least the drawdown limit from its
  peak
- **THEN** the system SHALL exit all open positions and stop the session

### Requirement: Bot value snapshots and performance KPIs

The system SHALL record a daily value snapshot for each active bot session capturing
its total value — **cash plus the marked-to-market value of all open positions** — and
realised and unrealised profit/loss aggregated across the session's positions, and SHALL
expose per-session KPIs computed from the ledger and snapshots (for example current
value, total return, and realised/unrealised profit/loss). These SHALL be computed
within the strategy-bots subsystem and SHALL NOT depend on the paper-trading subsystem's
persistence.

#### Scenario: Daily snapshot recorded

- **WHEN** the daily snapshot job runs for an active bot session
- **THEN** the system SHALL persist a value snapshot with the session's total value
  (cash plus all marked positions) and aggregated realised/unrealised profit/loss for
  that date

#### Scenario: KPIs computed from the session's own data

- **WHEN** a client requests a bot session's KPIs
- **THEN** the system SHALL return figures computed from that session's own ledger
  and snapshots, aggregated across its positions

### Requirement: Dashboard performance adapter for bot sessions

The strategy-bots subsystem SHALL expose active bot sessions to the dashboard in the
same per-session performance shape used for AI sessions, so the dashboard can render
them on shared axes without coupling to bot-specific persistence. For each active
bot session over a selected range this SHALL include a stable identifier, a display
label derived from the strategy and traded set, the allocated capital, the current
value **(cash plus all marked-to-market positions)**, the range profit/loss, fees,
realised and unrealised profit/loss, a value series windowed to the range, the
session's capital contributions, a since-inception benchmark buy-and-hold value computed
on the same basis as AI sessions, and a `kind` marker identifying the row as a bot.

#### Scenario: Bot row exposed in the shared performance shape

- **WHEN** the dashboard requests active-session performance for a range
- **THEN** each active bot session SHALL be returned in the same per-session
  performance shape as AI sessions, including its value series, contributions,
  since-inception benchmark value, and a `kind` marker identifying it as a bot

#### Scenario: Benchmark value basis matches AI sessions

- **WHEN** a bot session has a benchmark with priceable closes for its contributions
- **THEN** its since-inception benchmark value SHALL be computed on the same
  contribution-aware buy-and-hold basis used for AI sessions, so the two are
  directly comparable

## ADDED Requirements

### Requirement: Shared capital pool with ATR risk-based sizing and a hard budget ceiling

A bot session's capital SHALL be a single shared cash pool whose starting balance is the
session's initial capital budget. The sum of the cost of all open positions SHALL never
exceed the budget: the system SHALL open or extend a position only when its cost fits in
the session's **remaining** cash after the configured cash buffer, and exiting a position
SHALL return its proceeds to the shared pool so the freed capital is available to other
symbols. The system SHALL size each new long position by one of the configured sizing
methods: an **ATR risk-based** method that targets an equal dollar risk per position
(risk dollars computed as a configured fraction of the budget, divided by a configured
multiple of the symbol's Average True Range) and an **all-in** method (the greatest whole
number of shares affordable from available cash). Every computed size SHALL additionally
be bounded by a configured **maximum per-name fraction of the budget** and by remaining
cash, and SHALL be a whole number of shares; a size below one share SHALL result in no
trade. The system SHALL hold at most one open position per symbol (no pyramiding) and
SHALL enforce a configured **maximum number of concurrent open positions** per session.
Trades SHALL be long-only; short positions SHALL never be opened. On an EXIT the system
SHALL sell the entire position. Each executed buy and sell SHALL be recorded in the
session's trade ledger with its filled price and quantity.

#### Scenario: Total deployed capital never exceeds the budget

- **WHEN** more symbols signal entry on a tick than the remaining cash can fund
- **THEN** the system SHALL fund entries only while they fit within remaining cash and
  SHALL skip the rest, so the sum of open-position cost never exceeds the budget

#### Scenario: ATR risk-based sizing targets equal dollar risk

- **WHEN** a session using ATR risk-based sizing enters a position
- **THEN** the share quantity SHALL be the configured risk dollars divided by the
  configured multiple of the symbol's ATR, floored to whole shares, and SHALL be smaller
  for a higher-volatility symbol than for a lower-volatility one at the same price

#### Scenario: Per-name cap and cash bound every size

- **WHEN** a sized position would exceed the maximum per-name fraction of the budget or
  the available cash
- **THEN** the system SHALL reduce the quantity to satisfy both bounds, and SHALL open no
  position if fewer than one share is affordable

#### Scenario: Maximum concurrent positions is enforced

- **WHEN** a session already holds its maximum number of concurrent open positions and
  another symbol signals entry
- **THEN** the system SHALL NOT open the additional position

#### Scenario: Freed capital is reusable within the same tick

- **WHEN** a position is exited earlier in a tick and another symbol signals entry later
  in the same tick
- **THEN** the proceeds returned to the shared pool SHALL be available to fund that
  later entry

#### Scenario: Exited capital releases and no pyramiding

- **WHEN** a symbol with an open position signals entry again
- **THEN** the system SHALL NOT add to the existing position

## REMOVED Requirements

### Requirement: Long-only all-in position sizing and execution

This requirement is replaced by "Shared capital pool with ATR risk-based sizing and a
hard budget ceiling": a session no longer sizes a single all-in position against one
asset's capital, but sizes multiple positions from a shared, hard-capped cash pool using
a configurable sizing method (ATR risk-based or all-in) bounded by a per-name cap,
remaining cash, and a maximum-concurrent-positions limit.
