# strategy-bots Specification

## Purpose

Deterministic, rule-based (non-AI) technical-indicator trading bots that trade the
shared asset universe on Alpaca paper, run on a cron-triggered intraday tick, and
are tracked separately from AI paper-trading while remaining comparable with it on
the dashboard.

## Requirements

### Requirement: Strategy bot session lifecycle

The system SHALL let a client create a strategy-bot session bound to a single
strategy, a single equity asset drawn from the shared asset universe, an initial
capital amount, a benchmark, and the strategy's parameters. A bot session SHALL be
persisted independently of AI paper-trading sessions, with no foreign key to
paper-trading sessions. A bot session SHALL have a lifecycle status of active,
stopped, or archived. The system SHALL let a client stop an active session and
archive a stopped session. Creating a bot session SHALL NOT invoke any AI model.

#### Scenario: Create a bot session

- **WHEN** a client creates a bot session with a valid strategy key, a universe
  asset, an initial capital, a benchmark, and valid strategy parameters
- **THEN** the system SHALL persist a new active bot session and return it, without
  invoking any AI model

#### Scenario: Reject an unknown strategy or non-universe asset

- **WHEN** a client creates a bot session with an unregistered strategy key, or an
  asset that is not an eligible equity in the universe
- **THEN** the system SHALL reject the request rather than creating a session

#### Scenario: Stop and archive

- **WHEN** a client stops an active bot session and later archives it
- **THEN** the session SHALL transition active → stopped → archived and SHALL no
  longer be ticked once stopped

### Requirement: Strategy registry and MA Crossover strategy

The system SHALL maintain a registry mapping each strategy key to its
implementation, its parameter schema, and the number of historical bars it
requires. Each strategy SHALL be a pure signal generator that, given recent bars,
the current position, and parameters, returns one of ENTER_LONG, EXIT, or HOLD
together with a human-readable reason, performing no I/O and holding no persisted
state. The system SHALL provide an **MA Crossover** strategy: when the fast simple
moving average crosses above the slow simple moving average it SHALL signal
ENTER_LONG; when the fast average crosses back below the slow average it SHALL
signal EXIT; otherwise HOLD. With fewer bars than the strategy requires it SHALL
signal HOLD.

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

### Requirement: Cron-triggered tick with market-hours gating

The system SHALL expose a tick endpoint, guarded by the shared cron token, that
advances all active bot sessions. The endpoint SHALL be a no-op (processing no
sessions) when the equity market is closed per the broker clock. For each active
session the runner SHALL fetch the strategy's required history of bars at the
configured signal bar timeframe, recompute indicators fresh each tick, evaluate the
strategy, and act on the signal. The bars the runner evaluates SHALL be obtained
from the subsystem's configured market-data source and SHALL satisfy the
market-data freshness requirement below, so the signal is computed on data that is
current as of the tick rather than materially stale relative to the tick cadence.
The runner SHALL hold no in-memory state across ticks: only position state, the
trade ledger, and value snapshots are persisted. The tick interval and the signal
bar timeframe SHALL be configurable, defaulting to five minutes each.

#### Scenario: Reject an unauthenticated tick

- **WHEN** the tick endpoint is called without a valid cron token
- **THEN** the system SHALL reject the request and advance no sessions

#### Scenario: Market closed is a no-op

- **WHEN** the tick endpoint is called while the equity market is closed
- **THEN** the system SHALL process no sessions and record no trades

#### Scenario: Stateless recompute per tick

- **WHEN** the tick runner processes an active session
- **THEN** it SHALL fetch the required bar history, recompute indicators from those
  bars, and evaluate the strategy without relying on state carried from a prior
  tick

#### Scenario: Only active sessions are ticked

- **WHEN** the tick runner runs while some sessions are stopped or archived
- **THEN** it SHALL advance only active sessions

### Requirement: Market-data freshness for intraday ticks

The strategy-bots subsystem SHALL evaluate strategies on real-time market data that is
current as of the tick: the bars (and the price used for sizing, take-profit,
stop-loss, and drawdown checks) SHALL NOT lag the tick by more than the configured
signal bar timeframe. On the free market-data tier the subsystem SHALL obtain the
tick's bars from the real-time **IEX** feed by selecting that feed **explicitly**, and
SHALL NOT depend for the current tick on the consolidated (SIP) feed, whose most recent
~15 minutes are restricted on the free tier and would otherwise make the tick act on
data staler than the signal interval. The market-data feed SHALL be configurable so a
deployment holding a real-time consolidated-feed subscription can select it instead.

Because the real-time IEX feed covers a single exchange (a small share of total
volume) and may have no trade in a given interval, the most recent bar MAY be sparse or
missing. The subsystem SHALL treat an absent or stale most-recent bar as "fresh data
unavailable" for that session and SHALL skip the session for that tick — trading no
stale signal and leaving its position and ledger unchanged — rather than acting on data
that violates the freshness bound.

#### Scenario: Tick acts on data current to the cadence

- **WHEN** the tick runner evaluates an active session
- **THEN** the bars and price it uses SHALL be current as of the tick, not lagging by
  more than the configured signal bar timeframe

#### Scenario: Real-time feed is selected explicitly, not the restricted default

- **WHEN** the tick runner fetches bars on the free market-data tier
- **THEN** it SHALL explicitly request the real-time IEX feed and SHALL NOT use the
  consolidated feed whose most recent minutes are restricted

#### Scenario: Missing fresh data skips the session rather than trading stale

- **WHEN** a fresh most-recent bar satisfying the freshness bound is unavailable for a
  session on a tick (for example the IEX feed has no recent trade for the symbol)
- **THEN** the system SHALL skip that session for the tick rather than act on stale
  data, and SHALL leave its position and ledger unchanged

### Requirement: Long-only all-in position sizing and execution

On an ENTER_LONG signal for a session with no open position, the system SHALL size
a single long position as the greatest whole number of shares affordable from the
session's available capital after reserving a cash buffer, i.e.
`floor((capital - buffer) / price)`, and submit a buy for that quantity, polling
until the order reaches a terminal fill state. The system SHALL hold at most one
position per session and SHALL NOT add to an existing position (no pyramiding or
scaling-in). On an EXIT signal for a session with an open position, the system
SHALL sell the entire position and poll until terminal. Trades SHALL be long-only;
short positions SHALL never be opened. Each executed buy and sell SHALL be recorded
in the session's trade ledger with its filled price and quantity.

#### Scenario: Enter sizes whole shares within the cash buffer

- **WHEN** an ENTER_LONG signal fires for a session with no open position
- **THEN** the system SHALL buy `floor((capital - buffer) / price)` whole shares and
  record the fill

#### Scenario: No pyramiding

- **WHEN** an ENTER_LONG signal fires for a session that already holds a position
- **THEN** the system SHALL NOT increase the position

#### Scenario: Exit sells the whole position

- **WHEN** an EXIT signal fires for a session holding a position
- **THEN** the system SHALL sell the entire quantity and record the fill

#### Scenario: Never opens a short

- **WHEN** any signal would require selling more than the held quantity
- **THEN** the system SHALL NOT open a short position

### Requirement: Optional take-profit, stop-loss, and drawdown kill-switch

A bot session MAY configure an optional take-profit and an optional stop-loss as
percentage thresholds against the open position's entry price; when unset, neither
triggers. On each tick for a session with an open position, the system SHALL exit
the position if the current price has risen to or above the take-profit threshold or
fallen to or below the stop-loss threshold, independently of the strategy signal.
The system SHALL also enforce a drawdown kill-switch: when a session's value falls
by at least the configured drawdown limit from its peak, the system SHALL exit any
open position and stop the session so it is no longer ticked.

#### Scenario: Take-profit exits

- **WHEN** a session with an open position and a configured take-profit ticks at a
  price at or above the take-profit threshold
- **THEN** the system SHALL exit the position regardless of the strategy signal

#### Scenario: Stop-loss exits

- **WHEN** a session with an open position and a configured stop-loss ticks at a
  price at or below the stop-loss threshold
- **THEN** the system SHALL exit the position regardless of the strategy signal

#### Scenario: Thresholds unset never trigger

- **WHEN** a session has no take-profit and no stop-loss configured
- **THEN** neither a take-profit nor a stop-loss exit SHALL occur

#### Scenario: Drawdown kill-switch stops the session

- **WHEN** a session's value has fallen by at least the drawdown limit from its peak
- **THEN** the system SHALL exit any open position and stop the session

### Requirement: Bot value snapshots and performance KPIs

The system SHALL record a daily value snapshot for each active bot session capturing
its total value (cash plus the marked-to-market position) and realised and
unrealised profit/loss, and SHALL expose per-session KPIs computed from the ledger
and snapshots (for example current value, total return, and realised/unrealised
profit/loss). These SHALL be computed within the strategy-bots subsystem and SHALL
NOT depend on the paper-trading subsystem's persistence.

#### Scenario: Daily snapshot recorded

- **WHEN** the daily snapshot job runs for an active bot session
- **THEN** the system SHALL persist a value snapshot with the session's total value
  and realised/unrealised profit/loss for that date

#### Scenario: KPIs computed from the session's own data

- **WHEN** a client requests a bot session's KPIs
- **THEN** the system SHALL return figures computed from that session's own ledger
  and snapshots

### Requirement: Dashboard performance adapter for bot sessions

The strategy-bots subsystem SHALL expose active bot sessions to the dashboard in the
same per-session performance shape used for AI sessions, so the dashboard can render
them on shared axes without coupling to bot-specific persistence. For each active
bot session over a selected range this SHALL include a stable identifier, a display
label derived from the strategy and traded asset, the allocated capital, the current
value, the range profit/loss, fees, realised and unrealised profit/loss, a value
series windowed to the range, the session's capital contributions, a since-inception
benchmark buy-and-hold value computed on the same basis as AI sessions, and a `kind`
marker identifying the row as a bot.

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
