# strategy-bots Specification

## Purpose

Deterministic, rule-based (non-AI) technical-indicator trading bots that trade the
shared asset universe on Alpaca paper, run on a cron-triggered intraday tick, and
are tracked separately from AI paper-trading while remaining comparable with it on
the dashboard.

## Requirements

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
client stop an active session and archive a stopped session. Whenever a session
transitions to stopped — by a manual stop, the drawdown kill-switch, or a bot
orchestrator — the system SHALL record the **stop reason** (manual, drawdown
kill-switch, or orchestrator) and the **stop time**. Sessions that were already stopped
before this behavior existed MAY have an absent stop reason and stop time. Creating a
bot session through the client API SHALL NOT invoke any AI model.

**Stopping sells.** A stopped session SHALL end up flat. When a session is stopped by any
path, every position it still holds SHALL be sold at market by the intraday tick while
the market is open — on the first tick after the stop, or on the next market-open tick if
the market is closed. This SHALL apply to stopped and archived sessions that still hold
positions, including sessions stopped before this behaviour existed. Once stopped, a
session SHALL NOT open new positions.

A client MAY create a session **from a preset** by supplying a preset key. The strategy
is then the preset's strategy; if the client also supplies a strategy key, it SHALL match
the preset's strategy. The preset SHALL provide the strategy parameters and the take-profit,
stop-loss, and drawdown limit for any of those values the client does not supply; values
the client supplies SHALL override the preset's, including explicitly turning take-profit
or stop-loss off. The session SHALL record the preset key and whether its effective
strategy parameters or risk controls differ from the preset's (**customized**). A session
created without a preset SHALL record no preset key. Every session SHALL record its
**origin**: sessions created through the client API SHALL have origin manual, sessions
deployed by a bot orchestrator SHALL have origin orchestrator together with a reference to
that orchestrator, and sessions that existed before origin was recorded SHALL be treated
as manual. Session reads SHALL report the preset key, the customized flag, the origin, and
the deploying orchestrator (absent for manual sessions).

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
  longer be ticked for new entries once stopped

#### Scenario: Manual stop records reason and time

- **WHEN** a client manually stops an active bot session
- **THEN** the system SHALL record the stop reason as manual and the stop time as the
  moment it stopped

#### Scenario: Stopping sells open positions at the next market-open tick

- **WHEN** a session holding open positions is stopped and an intraday tick then runs
  while the market is open
- **THEN** the tick SHALL sell every position the session holds at market, record the
  sells in the session's trade ledger, and leave the session flat and stopped

#### Scenario: Stop while the market is closed sells at the next open

- **WHEN** a session holding open positions is stopped while the market is closed
- **THEN** the session SHALL be stopped immediately and its positions SHALL be sold by the
  first tick after the market opens

#### Scenario: Previously stopped sessions with positions are flattened

- **WHEN** an intraday tick runs while the market is open and a stopped or archived session
  still holds positions from before stopping sold
- **THEN** the tick SHALL sell those positions

#### Scenario: Stopped session opens no new positions

- **WHEN** an intraday tick runs for a stopped session
- **THEN** the system SHALL NOT evaluate entries or open any position for it

#### Scenario: Create from a preset without overrides

- **WHEN** a client creates a session supplying a preset key, assets, capital, and a
  benchmark, but no strategy parameters or risk controls
- **THEN** the session SHALL use the preset's strategy, strategy parameters, take-profit,
  stop-loss, and drawdown limit, and SHALL record the preset key as not customized with
  origin manual

#### Scenario: Create from a preset with overrides

- **WHEN** a client creates a session supplying a preset key and a strategy parameter or
  risk control that differs from the preset's
- **THEN** the session SHALL use the supplied value, keep the preset's values for
  everything not supplied, and record the preset key as customized

#### Scenario: Supplied values equal to the preset are not customized

- **WHEN** a client creates a session supplying a preset key together with values that
  all equal the preset's
- **THEN** the session SHALL record the preset key as not customized

#### Scenario: Reject an unknown preset or mismatched strategy

- **WHEN** a client creates a session with an unknown preset key, or with a strategy key
  that differs from the preset's strategy
- **THEN** the system SHALL reject the request rather than creating a session

#### Scenario: Create without a preset

- **WHEN** a client creates a session without a preset key
- **THEN** the session SHALL be created exactly as before, recording no preset key, not
  customized, and origin manual

#### Scenario: Orchestrator-deployed session records its origin

- **WHEN** a bot orchestrator deploys a session
- **THEN** the session SHALL record origin orchestrator and the deploying orchestrator, and
  session reads SHALL report both

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

### Requirement: Optional take-profit, stop-loss, and drawdown kill-switch

A bot session MAY configure an optional take-profit and an optional stop-loss as
percentage thresholds against each open position's entry price; when unset, neither
triggers. On each tick, for **every open position** the system SHALL exit that position
if its current price has risen to or above the take-profit threshold or fallen to or
below the stop-loss threshold, independently of the strategy signal. The system SHALL
also enforce a **whole-session** drawdown kill-switch: when a session's total value
falls by at least the configured drawdown limit from its peak, the system SHALL exit
**all** open positions and stop the session so it is no longer ticked. When the
kill-switch stops a session it SHALL record the **stop reason** as drawdown kill-switch
and the **stop time**. A session deployed by a bot orchestrator SHALL keep its own
take-profit, stop-loss and kill-switch, independently of the orchestrator's decisions.

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
- **THEN** the system SHALL exit all open positions and stop the session, and SHALL
  record the stop reason as drawdown kill-switch and the stop time

#### Scenario: Orchestrator-deployed session keeps its own kill-switch

- **WHEN** a session deployed by a bot orchestrator reaches its drawdown limit
- **THEN** the system SHALL exit all its positions and stop it with stop reason drawdown
  kill-switch, without waiting for an orchestrator decision

### Requirement: Bot value snapshots and performance KPIs

The system SHALL record a daily value snapshot for each active bot session capturing
its total value — **cash plus the marked-to-market value of all open positions** — and
realised and unrealised profit/loss aggregated across the session's positions, and SHALL
expose per-session KPIs computed from the ledger and snapshots (for example current
value, **available (free, uninvested) cash**, total return, realised/unrealised
profit/loss, the session's **best and worst closed round-trip trade**, and a
**benchmark comparison** against the session's configured benchmark index). These SHALL
be computed within the strategy-bots subsystem and SHALL NOT depend on the paper-trading
subsystem's persistence.

The session's **current value** — and the unrealised profit/loss reported alongside it —
SHALL reflect the **most recently captured value observation**: the latest per-tick
intraday value point when it is more recent than the latest daily snapshot, otherwise the
latest daily snapshot, otherwise cash plus open positions valued at cost when the session
has neither. The KPIs SHALL additionally expose the **as-of timestamp** of that
observation and whether it came from an intraday value point, and SHALL expose a separate
**end-of-day value** equal to the session's latest daily snapshot total value, reported as
absent when the session has no snapshot yet. No live broker or quote call SHALL be made to
produce these figures.

A closed round-trip trade is an entry (buy) paired with the exit (sell) that fully closes
that position; its realized P&L is the exit proceeds minus the entry cost (net of fees).
The **best** closed round-trip is the one with the highest realized P&L and the **worst**
is the one with the lowest; each SHALL be reported with its ticker, realized P&L, and the
round-trip's **entry price and time**, **exit price and time**, and **quantity**. When
the session has no closed round-trip yet (no completed exit), the best and worst trade
SHALL be reported as absent.

The **benchmark comparison** SHALL report the session's configured benchmark id, the
benchmark's since-inception buy-and-hold return as a fraction, and the session's **excess
return** as a fraction (the session's total return fraction minus the benchmark's return
fraction). The benchmark return and excess return SHALL be reported as absent when the
session has no value snapshot yet or the benchmark lacks usable stored closes for the
period, computed on the same basis as the session's daily-notification benchmark
comparison.

#### Scenario: Daily snapshot recorded

- **WHEN** the daily snapshot job runs for an active bot session
- **THEN** the system SHALL persist a value snapshot with the session's total value
  (cash plus all marked positions) and aggregated realised/unrealised profit/loss for
  that date

#### Scenario: KPIs computed from the session's own data

- **WHEN** a client requests a bot session's KPIs
- **THEN** the system SHALL return figures computed from that session's own ledger
  and snapshots, aggregated across its positions

#### Scenario: Current value and unrealised P&L track the freshest observation

- **WHEN** a client requests a bot session's KPIs and the session's latest intraday value
  point is more recent than its latest daily snapshot
- **THEN** the returned current value and unrealised profit/loss SHALL be taken from that
  intraday value point, and the KPIs SHALL mark the value as intraday with the value
  point's capture time as its as-of timestamp

#### Scenario: Current value falls back to the latest snapshot

- **WHEN** a client requests a bot session's KPIs and the latest daily snapshot is at
  least as recent as any intraday value point (for example after the end-of-day snapshot
  job, or when no intraday point exists)
- **THEN** the returned current value and unrealised profit/loss SHALL be taken from that
  daily snapshot, and the KPIs SHALL mark the value as not intraday with the snapshot's
  timestamp as its as-of timestamp

#### Scenario: Current value before any snapshot or value point

- **WHEN** a client requests the KPIs for a session that has neither a daily snapshot nor
  an intraday value point yet
- **THEN** the returned current value SHALL be cash plus open positions valued at cost,
  its unrealised profit/loss SHALL be zero, and its as-of timestamp SHALL be absent

#### Scenario: KPIs include a separate end-of-day value

- **WHEN** a client requests the KPIs for a session that has at least one daily snapshot
- **THEN** the returned KPIs SHALL include an end-of-day value equal to the session's
  latest daily snapshot total value, distinct from the (possibly intraday) current value

#### Scenario: End-of-day value absent before any snapshot

- **WHEN** a client requests the KPIs for a session that has no daily snapshot yet
- **THEN** the returned end-of-day value SHALL be reported as absent

#### Scenario: KPIs include available cash

- **WHEN** a client requests a bot session's KPIs
- **THEN** the returned KPIs SHALL include the session's available (free, uninvested)
  cash balance — the cash not currently deployed in open positions

#### Scenario: KPIs include best and worst closed trade

- **WHEN** a client requests the KPIs for a session that has at least one closed
  round-trip trade
- **THEN** the returned KPIs SHALL include the best closed round-trip and the worst closed
  round-trip, each with its ticker, realized P&L, entry price and time, exit price and
  time, and quantity

#### Scenario: Best and worst trade absent before any closed round-trip

- **WHEN** a client requests the KPIs for a session that has no closed round-trip trade
  yet (no completed exit)
- **THEN** the returned KPIs SHALL report the best and worst closed round-trip as absent

#### Scenario: KPIs include benchmark and excess return

- **WHEN** a client requests the KPIs for a session that has at least one value snapshot
  and a benchmark with usable stored closes
- **THEN** the returned KPIs SHALL include the session's benchmark id, the benchmark's
  since-inception buy-and-hold return fraction, and the session's excess return fraction
  (the session's total return fraction minus the benchmark's)

#### Scenario: Benchmark comparison absent without snapshots or prices

- **WHEN** a client requests the KPIs for a session that has no value snapshot yet, or
  whose benchmark lacks usable stored closes for the period
- **THEN** the returned KPIs SHALL still include the benchmark id but SHALL report the
  benchmark return and excess return as absent

### Requirement: Bot daily summary notification

When the daily bot snapshot job records an active session's snapshot, the system SHALL
send that session a **best-effort daily summary notification**, titled with the bot's
label, mirroring the AI portfolios' daily report: its value and day-over-day change (amount
and percentage, against the previous snapshot or, on the first day, its allocated capital;
the percentage omitted when that baseline is not positive), its total return (amount and
percentage), realised and unrealised P&L, cash, fees, Sharpe ratio, a benchmark comparison
when available, its best and worst open position when it has any, and the number of trades
it executed that day.

Sessions **deployed by a bot orchestrator** SHALL still be snapshotted but SHALL NOT send
their own daily summary notification; their orchestrator's daily notification covers them.
Manually created sessions SHALL keep their own notification.

The notification SHALL be a silent no-op when no notification channel is configured, and a
notification failure SHALL NOT fail the snapshot job.

#### Scenario: Daily summary notification sent per manual bot

- **WHEN** the daily snapshot job runs for an active, manually created bot session
- **THEN** the system SHALL send one notification for that session carrying its value and
  day change, total return, realised and unrealised P&L, cash, fees, Sharpe ratio, benchmark
  comparison when available, best and worst open position, and the day's trade count

#### Scenario: Orchestrator-deployed bots are snapshotted without their own push

- **WHEN** the daily snapshot job runs for an active session deployed by an orchestrator
- **THEN** the system SHALL record its daily snapshot and SHALL NOT send it a daily summary
  notification

#### Scenario: Summary notification is best-effort and silent when unconfigured

- **WHEN** the snapshot job runs while no notification channel is configured, or while a
  configured channel fails
- **THEN** the snapshots SHALL still be recorded and the job SHALL NOT fail because of the
  (absent or failed) notification

### Requirement: Bot kill-switch notification

When the drawdown kill-switch stops a bot session during a tick, the system SHALL send one
**best-effort notification** titled with the bot's label, stating that the drawdown
kill-switch tripped, naming the positions it liquidated (their count and tickers, or that
there were no open positions to liquidate), the realised P&L booked on that liquidation, and
that the bot is now stopped. The notification SHALL be sent for every bot whose kill-switch
trips, including bots deployed by a bot orchestrator. It SHALL be a silent no-op when no
notification channel is configured, and a notification failure SHALL NOT prevent the
kill-switch from liquidating and stopping the bot or fail the tick. A tick in which no
kill-switch trips SHALL send no kill-switch notification.

#### Scenario: Kill-switch sends one notification

- **WHEN** a tick trips a bot's drawdown kill-switch while it holds two positions
- **THEN** the system SHALL send one notification titled with the bot's label that names
  both liquidated positions, the realised P&L of the liquidation, and that the bot is now
  stopped

#### Scenario: Kill-switch with no open positions

- **WHEN** a bot's kill-switch trips while it holds no open positions
- **THEN** the notification SHALL state that there were no open positions to liquidate

#### Scenario: No trip, no notification

- **WHEN** a tick processes a bot whose drawdown stays within its limit
- **THEN** no kill-switch notification SHALL be sent

#### Scenario: Notification failure does not block the stop

- **WHEN** the kill-switch trips while the notification channel is absent or fails
- **THEN** the bot SHALL still be liquidated and stopped, and the tick SHALL NOT fail

### Requirement: Bot display name

Every bot session SHALL have a **display name** used consistently wherever a bot is named —
the Bots list, the bot detail header, its dashboard row, and its notification titles. The
display name SHALL be the session's label when it has one; otherwise it SHALL be the display
name of the preset it started from (or, without a preset, the strategy's display name)
followed by its traded set — the ticker when it trades one, otherwise the number of symbols
it trades. Internal strategy keys (such as `donchian_breakout`) SHALL NOT
be shown as a bot's name.

#### Scenario: Unlabelled preset bot

- **WHEN** a bot without a label was created from the Turtle Breakout (Algo 25) preset and
  trades MSFT
- **THEN** its display name SHALL be "Turtle Breakout (Algo 25) · MSFT" on the Bots list, its
  detail header and its notification titles

#### Scenario: Unlabelled custom bot

- **WHEN** a bot without a label and without a preset uses the Donchian range-breakout strategy
- **THEN** its display name SHALL use the strategy's display name, "Donchian Range Breakout",
  followed by its traded set

#### Scenario: Bot trading several symbols

- **WHEN** an unlabelled bot from the RSI Mean Reversion (Algo 16) preset trades three symbols
- **THEN** its display name SHALL be "RSI Mean Reversion (Algo 16) · 3 symbols"

#### Scenario: Labelled bot

- **WHEN** a bot has a label
- **THEN** its display name SHALL be that label

### Requirement: Session-list current value

When the system lists bot sessions, each listed session SHALL include a **live value** —
cash plus the marked-to-market value of its open positions — derived from the most recently
captured value observation on the same basis as the per-session current-value KPI: the
latest intraday value point when more recent than the latest daily snapshot, otherwise the
latest daily snapshot, otherwise cash plus open positions valued at cost. Each listed
session SHALL additionally include a separate **end-of-day value** equal to its latest
daily snapshot total value, reported as absent when the session has no snapshot yet.

#### Scenario: Listed session carries its current value

- **WHEN** a client lists bot sessions
- **THEN** each listed session SHALL include its live value, derived from the most recently
  captured value observation (latest intraday value point when more recent than the latest
  daily snapshot, otherwise the latest snapshot)

#### Scenario: Listed session carries its end-of-day value

- **WHEN** a client lists bot sessions and a session has at least one daily snapshot
- **THEN** that listed session SHALL include an end-of-day value equal to its latest daily
  snapshot total value, distinct from its live value

#### Scenario: Current value before any snapshot exists

- **WHEN** a session that has not yet recorded a value snapshot is listed
- **THEN** its live value SHALL be reported as cash plus its open positions valued at cost,
  and its end-of-day value SHALL be reported as absent

### Requirement: Open-positions sort order on the bot detail view

When presenting a bot session's open positions, the system SHALL let the viewer order the
positions either by ticker (the default) or by the timestamp each position was opened. The
selected ordering SHALL affect only presentation and SHALL NOT change which positions are
shown or any position's data.

#### Scenario: Default ordering by ticker

- **WHEN** a viewer opens a bot session's open-positions view without choosing a sort order
- **THEN** the positions SHALL be ordered by ticker

#### Scenario: Ordering by opened timestamp

- **WHEN** a viewer chooses to sort the open positions by opened timestamp
- **THEN** the positions SHALL be ordered by the time each position was opened, with the
  same positions and data as the ticker ordering

### Requirement: Bot detail performance tiles

The bot detail view's performance section SHALL present the session's KPIs as tiles,
including a distinct **live-value tile** (the session's most recently captured value,
annotated with its as-of basis) and **end-of-day-value tile** (the session's latest daily
snapshot value, or a neutral placeholder when no snapshot exists yet), and a
**benchmark-comparison tile** that shows the session's excess return as its primary figure
and the benchmark's own return as a secondary figure, labelled with the benchmark's display
name. The performance section SHALL NOT present a transaction-fees tile, SHALL NOT present a
separate allocated-capital tile (the allocated capital is already shown in the session
header), and SHALL NOT label the whole performance section with a single freshness
indicator — instead **each performance tile** SHALL carry its own freshness badge.

Each performance tile's badge SHALL mark its figure as either **live** (marked-to-market
and updating through the trading day) or **end-of-day** (derived from the latest daily
snapshot, updating once per day after the close). Tiles whose figures derive from the
daily snapshot series — the end-of-day-value, maximum-drawdown, Sharpe-ratio, and
benchmark-comparison tiles — SHALL be marked end-of-day; the remaining current /
marked-to-market tiles SHALL be marked live. The live-value, total-return, and
unrealised-P&L tiles — whose figures come from the most recently captured value
observation — SHALL reflect that observation's actual basis: live when it came from an
intraday value point, end-of-day otherwise.

When the benchmark comparison is unavailable (the session has no snapshot yet or the
benchmark lacks usable closes), the benchmark-comparison tile SHALL render a neutral
placeholder in place of the figures rather than an error.

#### Scenario: Distinct live and end-of-day value tiles shown

- **WHEN** a client views the performance section for a session
- **THEN** the section SHALL show a live-value tile and a separate end-of-day-value tile,
  and SHALL NOT show an allocated-capital tile or a single section-level freshness badge

#### Scenario: Each performance tile carries a freshness badge

- **WHEN** a client views the performance section for a session
- **THEN** every performance tile SHALL carry a badge marking it as either live or
  end-of-day, with the end-of-day-value, maximum-drawdown, Sharpe-ratio, and
  benchmark-comparison tiles marked end-of-day and the remaining marked-to-market tiles
  marked live

#### Scenario: Observation-derived tiles reflect the live value's basis

- **WHEN** a client views the performance section and the session's current value came
  from an intraday value point
- **THEN** the live-value, total-return, and unrealised-P&L tiles SHALL be badged live;
  and when the current value instead came from a daily snapshot, those tiles SHALL be
  badged end-of-day

#### Scenario: End-of-day-value tile placeholder before any snapshot

- **WHEN** a client views the performance section for a session that has no daily snapshot
  yet
- **THEN** the end-of-day-value tile SHALL render a neutral placeholder instead of a value

#### Scenario: Benchmark-comparison tile shown

- **WHEN** a client views the performance section for a session whose KPIs include a
  benchmark and excess return
- **THEN** the section SHALL show a benchmark-comparison tile with the excess return as
  its primary figure and the benchmark return as a secondary figure, and SHALL NOT show
  a transaction-fees tile

#### Scenario: Benchmark-comparison tile placeholder

- **WHEN** a client views the performance section for a session whose benchmark return is
  absent
- **THEN** the benchmark-comparison tile SHALL render a neutral placeholder instead of the
  figures

### Requirement: Dashboard performance adapter for bot sessions

The strategy-bots subsystem SHALL expose active **manually created** bot sessions to the dashboard in the
same per-session performance shape used for AI sessions, so the dashboard can render
them on shared axes without coupling to bot-specific persistence. Bot sessions deployed by a bot orchestrator SHALL NOT be exposed as rows of their own;
they are represented through their orchestrator. For each exposed
bot session over a selected range this SHALL include a stable identifier, its display
name, the allocated capital, the current
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

#### Scenario: Orchestrator-deployed bots are not exposed

- **WHEN** the dashboard requests active-session performance while an orchestrator has an
  active bot
- **THEN** that bot SHALL NOT be returned as a row of its own

### Requirement: Paginated trade-ledger reads

The system SHALL expose a bot session's trade ledger through a paginated read API.
A request MAY specify a zero-based `offset` and a `limit`; the system SHALL default
the limit to 20 and SHALL reject a limit above 100 or a negative offset/limit with a
`422` response. The system SHALL return a single page of trades ordered by execution
time most-recent-first, together with the full count of the session's trades so the
client can determine how many pages exist. The system SHALL NOT require loading the
entire ledger into memory to serve a page. An unknown session SHALL return `404`.

#### Scenario: Default page returns the most recent trades

- **WHEN** a client requests a known session's trades without pagination parameters
- **THEN** the system SHALL return at most the default page size of trades, ordered
  most-recent-first, and a `total` equal to the session's full trade count

#### Scenario: Offset and limit select a bounded page

- **WHEN** a client requests a known session's trades with a valid `offset` and
  `limit`
- **THEN** the system SHALL return only the trades in that window, still ordered
  most-recent-first, with `total` unchanged as the full count

#### Scenario: Invalid pagination parameters are rejected

- **WHEN** a client requests trades with a negative offset or limit, or a limit above
  the maximum of 100
- **THEN** the system SHALL respond with `422` and SHALL NOT return a page

#### Scenario: Unknown session

- **WHEN** a client requests trades for a session id that does not exist
- **THEN** the system SHALL respond with `404`

### Requirement: Intraday value-point capture at each tick

In addition to the daily value snapshot, the system SHALL persist a timestamped
intraday value point for every active bot session it processes on a tick, capturing the
session's total value — **cash plus the marked-to-market value of all open positions** —
and its aggregated realised and unrealised profit/loss at that tick's time. Capture is
forward-only: the system SHALL NOT reconstruct intraday points for ticks that happened
before this capability existed. When a tick processes no sessions (for example the
market is closed), the system SHALL record no intraday points. Capture failures SHALL
NOT be introduced into the trading path in a way that changes position or ledger
outcomes.

#### Scenario: Intraday point recorded per processed session

- **WHEN** a tick processes an active bot session during market hours
- **THEN** the system SHALL persist an intraday value point for that session stamped
  with the tick time, holding the session's total value (cash plus marked positions) and
  aggregated realised/unrealised profit/loss

#### Scenario: No points when nothing is processed

- **WHEN** a tick runs while the market is closed and processes no sessions
- **THEN** the system SHALL record no intraday value points

### Requirement: Intraday value-point retention

The system SHALL retain raw intraday value points for a bounded window of the most recent
30 days and SHALL prune points older than that window, so intraday storage does not grow
without limit. Pruning SHALL run as part of the once-daily snapshot job. Because the
`5min` and `hourly` resolutions are served from these raw points, both SHALL be bounded to
roughly this 30-day window; the `daily` and `monthly` resolutions are served from daily
snapshots and SHALL remain unbounded.

#### Scenario: Points older than the retention window are pruned

- **WHEN** the daily snapshot job runs
- **THEN** the system SHALL delete intraday value points older than the 30-day retention
  window and SHALL keep points within it

#### Scenario: Coarse resolutions are unaffected by intraday pruning

- **WHEN** intraday points older than 30 days have been pruned
- **THEN** the `daily` and `monthly` value-history resolutions SHALL still return the full
  recorded history from the daily snapshots

### Requirement: Multi-resolution value-history reads

The value-history read SHALL accept a resolution selector with the values `5min`,
`hourly`, `daily`, and `monthly`, and SHALL return the session's value series at the
requested resolution as points on a single uniform timestamped shape so one renderer can
display any resolution. `5min` SHALL return the raw intraday value points; `hourly` SHALL
downsample the intraday points to the last point within each clock hour; `daily` SHALL
return the recorded daily snapshots; `monthly` SHALL return the last recorded daily
snapshot within each calendar month. Each point SHALL carry its timestamp and total
value (and the realised/unrealised figures already exposed). The response SHALL indicate
which resolution it represents. An unrecognised resolution SHALL yield `422`; an unknown
session SHALL yield `404`. When the requested resolution has no data yet, the system
SHALL return an empty series rather than an error.

#### Scenario: Five-minute resolution returns intraday points

- **WHEN** a client requests a known session's value history at `5min` resolution
- **THEN** the system SHALL return the session's intraday value points, each with its
  timestamp and total value, oldest first

#### Scenario: Hourly resolution downsamples intraday points

- **WHEN** a client requests `hourly` resolution for a session with multiple intraday
  points inside the same clock hour
- **THEN** the system SHALL return one point per hour — the last point within each hour —
  each stamped with its timestamp and total value

#### Scenario: Daily and monthly resolutions use recorded snapshots

- **WHEN** a client requests `daily` or `monthly` resolution
- **THEN** the system SHALL return the daily snapshots (for `daily`) or the last daily
  snapshot per calendar month (for `monthly`), on the same timestamped point shape

#### Scenario: Unknown resolution is rejected

- **WHEN** a client requests value history with a resolution other than `5min`,
  `hourly`, `daily`, or `monthly`
- **THEN** the system SHALL respond with `422`

#### Scenario: Resolution with no data returns an empty series

- **WHEN** a client requests a resolution for which the session has no points yet (for
  example `5min` on a session created before intraday capture and not yet re-ticked)
- **THEN** the system SHALL return an empty series with the requested resolution, not an
  error

### Requirement: Bot value chart freshness indicator

The bot detail value chart SHALL display a freshness indicator whose meaning
reflects the currently selected resolution, so the label never contradicts the
data on screen. When an intraday resolution (`5min` or `hourly`) is selected —
the resolutions that plot per-tick intraday points — the indicator SHALL mark
the series as intraday, conveying that the latest point is the most recently
captured tick and can lag the live performance figures. When a coarse resolution
(`daily` or `monthly`) is selected — the resolutions that read the end-of-day
snapshot curve — the indicator SHALL mark the series as end-of-day. Switching the
resolution SHALL update the indicator accordingly.

#### Scenario: Coarse resolution marks the chart as end-of-day

- **WHEN** the bot value chart is shown at `daily` or `monthly` resolution
- **THEN** its freshness indicator SHALL mark the series as end-of-day

#### Scenario: Intraday resolution marks the chart as intraday

- **WHEN** the user selects the `5min` or `hourly` resolution for the bot value
  chart
- **THEN** its freshness indicator SHALL mark the series as intraday rather than
  end-of-day

#### Scenario: Switching back to a coarse resolution restores the end-of-day marker

- **WHEN** the user switches from an intraday resolution back to `daily` or
  `monthly`
- **THEN** the freshness indicator SHALL mark the series as end-of-day again

### Requirement: Bot value chart local-timezone labels

The bot detail value chart SHALL label its intraday (`5min` and `hourly`) axis ticks and
tooltips using the viewer's local timezone, so the chart's clock times agree with the trade
timestamps and live-value times shown elsewhere on the same page (which already render in
local time). For intraday resolutions the axis label SHALL be the point's local-time
`dd.MM HH:mm` and the tooltip SHALL be its local-time `dd.MM.yyyy HH:mm`, derived from the
point's captured instant rather than from UTC clock parts.

The `daily` and `monthly` resolutions SHALL label each point by its snapshot's calendar
date (no clock time). Each distinct calendar period SHALL appear on the x-axis **exactly
once** — one tick per snapshot date for `daily`, one tick per calendar month for `monthly`
— carrying that period's own end-of-day value. The labelling SHALL NOT depend on the
viewer's timezone: a date SHALL never be duplicated across multiple ticks, and a period's
value SHALL never be rendered under an adjacent period's label, for a viewer in any
timezone.

#### Scenario: Intraday axis and tooltip use local time

- **WHEN** the bot value chart is shown at `5min` or `hourly` resolution and a point was
  captured at an instant whose local-timezone clock time differs from its UTC clock time
- **THEN** the point's axis label SHALL be its local-time `dd.MM HH:mm` and its tooltip
  SHALL be its local-time `dd.MM.yyyy HH:mm` — matching the page's trade timestamps — and
  NOT the UTC clock value

#### Scenario: Daily and monthly remain calendar-date labels

- **WHEN** the bot value chart is shown at `daily` or `monthly` resolution
- **THEN** each point SHALL continue to be labelled by its snapshot's calendar date, with
  no clock-time component and no day shift

#### Scenario: Daily and monthly show one label per period

- **WHEN** the bot value chart is shown at `daily` or `monthly` resolution with points on
  consecutive distinct periods (for example daily snapshots on two consecutive dates)
- **THEN** each period SHALL appear exactly once on the x-axis, labelled by its own calendar
  date (`dd.MM`) with no clock-time component, each carrying that period's end-of-day value —
  no date duplicated across ticks and no value shown under an adjacent period's label

#### Scenario: Coarse labels are stable across viewer timezones

- **WHEN** the bot value chart is shown at `daily` or `monthly` resolution to a viewer whose
  local timezone is east or west of UTC
- **THEN** each snapshot SHALL be labelled by the same calendar date regardless of the
  viewer's timezone, with no day shift and no duplicated or misaligned labels

### Requirement: Bot value chart default resolution

When a viewer enters the bot detail page, the "Bot value" chart SHALL open at the
`5min` intraday resolution by default, so the first view is the live intraday series
rather than the coarse end-of-day snapshot curve. On this initial load the resolution
switcher SHALL reflect `5m` as the active selection and the freshness indicator SHALL
mark the series as intraday. The viewer SHALL still be able to switch to any other
supported resolution (`hourly`, `daily`, `monthly`); the chosen default does not remove
or reorder any switcher option.

#### Scenario: Chart opens at the 5-minute resolution

- **WHEN** a viewer enters the bot detail page and the value chart first loads
- **THEN** the chart SHALL request and display the `5min` intraday resolution, the
  resolution switcher SHALL show `5m` as the active selection, and the freshness
  indicator SHALL mark the series as intraday

#### Scenario: Viewer can still switch away from the default

- **WHEN** the value chart has opened at its `5min` default and the viewer selects a
  coarser resolution such as `daily`
- **THEN** the chart SHALL load that resolution and its freshness indicator SHALL mark
  the series as end-of-day, exactly as when any resolution is selected

### Requirement: RSI Mean Reversion strategy

The system SHALL provide an **RSI Mean Reversion** strategy, registered alongside
the existing strategies. It SHALL be a pure, long-only signal generator that, given
recent bars, the current position, and its parameters, returns one of ENTER_LONG,
EXIT, or HOLD together with a human-readable reason, performing no I/O and holding
no persisted state.

The strategy SHALL compute the Wilder-smoothed Relative Strength Index (RSI) of the
closing prices over a configurable `period`. Its behaviour SHALL be:

- when no position is open and the latest RSI is strictly below the `oversold`
  threshold, signal ENTER_LONG;
- when a long position is open and the latest RSI is strictly above the
  `exit_level` threshold, signal EXIT;
- otherwise signal HOLD.

The strategy SHALL be long-only: a high (overbought) RSI SHALL never open a short
position. Take-profit, stop-loss, and the drawdown kill-switch SHALL remain owned by
the engine and SHALL NOT be part of this strategy.

The strategy's parameters SHALL be `period` (a positive integer, default 14),
`oversold` (default 30) and `exit_level` (default 50), each a value on the RSI's
0–100 scale, with `oversold` strictly less than `exit_level`; invalid parameters
SHALL be rejected. The strategy SHALL require `period + 1` bars of history and, when
given fewer, SHALL signal HOLD rather than erroring. The strategy SHALL appear in
the strategy catalog with a display name and a human-readable explanation.

#### Scenario: Oversold RSI while flat enters long

- **WHEN** the RSI Mean Reversion strategy evaluates bars whose latest RSI is below
  the `oversold` threshold and no position is open
- **THEN** it SHALL return ENTER_LONG with a reason

#### Scenario: RSI reverting above the exit level exits

- **WHEN** the strategy evaluates bars whose latest RSI is above the `exit_level`
  threshold and a long position is open
- **THEN** it SHALL return EXIT with a reason

#### Scenario: RSI between thresholds holds

- **WHEN** the strategy evaluates bars whose latest RSI is at or above `oversold`
  (with no position) or at or below `exit_level` (while holding)
- **THEN** it SHALL return HOLD

#### Scenario: Overbought RSI never shorts

- **WHEN** the strategy evaluates bars whose latest RSI is high (overbought) and no
  position is open
- **THEN** it SHALL return HOLD rather than opening a short position

#### Scenario: Insufficient history holds

- **WHEN** the strategy is given fewer bars than its required history of `period + 1`
- **THEN** it SHALL return HOLD rather than erroring

#### Scenario: Invalid parameters are rejected

- **WHEN** a session is created with RSI parameters where `oversold` is not strictly
  less than `exit_level`, or a threshold is outside the 0–100 scale, or `period` is
  not a positive integer
- **THEN** the system SHALL reject the parameters with a validation error

#### Scenario: Catalog lists the RSI strategy

- **WHEN** a client requests the strategy catalog
- **THEN** the RSI Mean Reversion strategy SHALL be included with its display name,
  explanation, required history, and parameter schema

### Requirement: Donchian Range Breakout strategy

The system SHALL provide a **Donchian Range Breakout** strategy, registered
alongside the existing strategies. It SHALL be a pure, long-only signal generator
that, given recent bars, the current position, and its parameters, returns one of
ENTER_LONG, EXIT, or HOLD together with a human-readable reason, performing no I/O
and holding no persisted state.

The strategy SHALL expose a `version` parameter selecting one of two variants of
the same Donchian-channel-breakout indicator, computed over a window of bars that
**precede** the current bar (the current bar is excluded so a close can break out
of the channel):

- **Turtle rolling channel.** Behaviour:
  - when no position is open and the latest close is strictly above the highest
    high of the previous `entry_period` bars, signal ENTER_LONG;
  - when a long position is open and the latest close is strictly below the lowest
    low of the previous `exit_period` bars, signal EXIT;
  - otherwise signal HOLD.
- **Locked channel.** Behaviour:
  - when no position is open, compute the upper band as the highest high of the
    previous `channel_period` bars plus `atr_padding_mult × ATR` (where ATR is a
    simple average of the absolute successive close differences over the channel
    window; a padding multiplier of `0` yields the raw channel and a positive
    multiplier yields a false-breakout buffer), and signal ENTER_LONG when the
    latest close is strictly above that upper band;
  - when a long position is open, signal HOLD — the strategy emits no channel exit;
    exits are deferred entirely to the engine's take-profit / stop-loss bracket and
    drawdown kill-switch.

The strategy SHALL be long-only: a downward breakout SHALL never open a short
position. Take-profit, stop-loss, the drawdown kill-switch, and position sizing
SHALL remain owned by the engine and SHALL NOT be part of this strategy.

The strategy's parameters SHALL be `version` (`turtle` or `locked`, default
`turtle`), `entry_period` (a positive integer, default 20), `exit_period` (a
positive integer, default 10, strictly less than `entry_period`), `channel_period`
(a positive integer, default 20) and `atr_padding_mult` (a non-negative number,
default 0.5); invalid parameters SHALL be rejected. The strategy SHALL require
`entry_period + 1` bars of history in the Turtle version and `channel_period + 1`
bars in the Locked version and, when given fewer, SHALL signal HOLD rather than
erroring. The strategy SHALL appear in the strategy catalog with a display name and
a human-readable explanation describing both versions.

#### Scenario: Turtle upper breakout while flat enters long

- **WHEN** the Turtle version evaluates bars whose latest close is strictly above
  the highest high of the previous `entry_period` bars and no position is open
- **THEN** it SHALL return ENTER_LONG with a reason

#### Scenario: Turtle lower breakdown while holding exits

- **WHEN** the Turtle version evaluates bars whose latest close is strictly below
  the lowest low of the previous `exit_period` bars and a long position is open
- **THEN** it SHALL return EXIT with a reason

#### Scenario: Turtle price inside the channel holds

- **WHEN** the Turtle version evaluates bars whose latest close is at or below the
  entry high (with no position) or at or above the exit low (while holding)
- **THEN** it SHALL return HOLD

#### Scenario: Locked padded breakout while flat enters long

- **WHEN** the Locked version evaluates bars whose latest close is strictly above
  the highest high of the previous `channel_period` bars padded by
  `atr_padding_mult × ATR`, and no position is open
- **THEN** it SHALL return ENTER_LONG with a reason

#### Scenario: Locked while holding defers the exit to the engine

- **WHEN** the Locked version evaluates bars while a long position is open
- **THEN** it SHALL return HOLD, leaving the exit to the engine's take-profit /
  stop-loss bracket and drawdown kill-switch

#### Scenario: Downward breakout never shorts

- **WHEN** the strategy evaluates a downward breakout while no position is open
- **THEN** it SHALL return HOLD rather than opening a short position

#### Scenario: Insufficient history holds

- **WHEN** the strategy is given fewer bars than its required history (`entry_period
  + 1` for Turtle, `channel_period + 1` for Locked)
- **THEN** it SHALL return HOLD rather than erroring

#### Scenario: Invalid parameters are rejected

- **WHEN** a session is created with Donchian parameters where `exit_period` is not
  strictly less than `entry_period`, a period is not a positive integer,
  `atr_padding_mult` is negative, or `version` is not one of the allowed values
- **THEN** the system SHALL reject the parameters with a validation error

#### Scenario: Catalog lists the Donchian strategy with both versions

- **WHEN** a client requests the strategy catalog
- **THEN** the Donchian Range Breakout strategy SHALL be included with its display
  name, explanation describing both the Turtle and Locked versions, required
  history, and parameter schema

### Requirement: Rolling-Average Reversion strategy

The system SHALL provide a **Rolling-Average Reversion** strategy, registered alongside
the existing strategies. It SHALL be a pure, long-only signal generator that, given
recent bars, the current position, and its parameters, returns one of ENTER_LONG, EXIT,
or HOLD together with a human-readable reason, performing no I/O and holding no
persisted state.

The strategy SHALL compute a rolling **average** over the latest `window` bars,
including the current bar, using the configured `average_type`:

- `sma` — the arithmetic mean of the closes;
- `typical` — the arithmetic mean of the typical prices, (high + low + close) / 3;
- `vwap` — the volume-weighted average of the closes, Σ(close × volume) / Σ(volume).

It SHALL measure the latest close's distance below that average using the configured
`distance` measure:

- `band` — the fractional deviation (close − average) / average. While flat, the
  strategy SHALL signal ENTER_LONG when the deviation is strictly below
  −`entry_threshold`; an `entry_threshold` of 0 therefore enters on any close strictly
  below the average (a bare cross).
- `zscore` — (close − average) divided by the population standard deviation of the
  window's price series (the closes, or the typical prices for `typical`). While flat,
  the strategy SHALL signal ENTER_LONG when the z-score is strictly below −`entry_z`.

While a long position is open, behaviour SHALL follow `exit_mode`:

- `revert` — signal EXIT once the close has reverted to or above the exit level: a
  deviation at or above −`exit_threshold` for `band`, or a z-score at or above −`exit_z`
  for `zscore`. A close that overshoots above the average SHALL therefore also exit.
- `bracket` — signal HOLD, deferring every exit to the engine's take-profit / stop-loss
  bracket and drawdown kill-switch.

Otherwise the strategy SHALL signal HOLD. When the measure is undefined for the window —
zero total volume for `vwap`, or zero standard deviation for `zscore` — it SHALL signal
HOLD rather than erroring. The strategy SHALL be long-only: a close above the average
SHALL never open a short position. Take-profit, stop-loss, and the drawdown kill-switch
SHALL remain owned by the engine.

The strategy's parameters SHALL be `average_type` (`sma`, `typical` or `vwap`, default
`sma`), `window` (an integer of at least 2, default 20), `distance` (`band` or `zscore`,
default `band`), `entry_threshold` and `exit_threshold` (fractions of at least 0 and below
1, defaults 0.01 and 0.005), `entry_z` and `exit_z` (at least 0, defaults 1.0 and 0.2),
and `exit_mode` (`revert` or `bracket`, default `revert`). In `revert` mode the exit level
SHALL lie strictly above the entry level — `exit_threshold` strictly less than
`entry_threshold` for `band`, `exit_z` strictly less than `entry_z` for `zscore` —
otherwise the parameters SHALL be rejected. The strategy SHALL require `window` bars of
history and, when given fewer, SHALL signal HOLD rather than erroring. The strategy SHALL
appear in the strategy catalog with a display name and a human-readable explanation.

#### Scenario: Band entry below the average while flat

- **WHEN** the strategy evaluates bars with `distance` band whose latest close is more than
  `entry_threshold` below the rolling average and no position is open
- **THEN** it SHALL return ENTER_LONG with a reason

#### Scenario: Close within the band holds while flat

- **WHEN** the strategy evaluates bars with `distance` band whose latest close is at or
  above the entry level and no position is open
- **THEN** it SHALL return HOLD

#### Scenario: Zero band enters on a bare cross below the average

- **WHEN** the strategy evaluates bars with `distance` band and `entry_threshold` 0 whose
  latest close is strictly below the rolling average and no position is open
- **THEN** it SHALL return ENTER_LONG

#### Scenario: Z-score entry while flat

- **WHEN** the strategy evaluates bars with `distance` zscore whose latest z-score is
  strictly below −`entry_z` and no position is open
- **THEN** it SHALL return ENTER_LONG with a reason

#### Scenario: Revert exit once price returns toward the average

- **WHEN** the strategy evaluates bars in `revert` mode while a long position is open and
  the latest close has reverted to or above the exit level (including above the average)
- **THEN** it SHALL return EXIT with a reason

#### Scenario: Revert mode holds while still below the exit level

- **WHEN** the strategy evaluates bars in `revert` mode while a long position is open and
  the latest close is still below the exit level
- **THEN** it SHALL return HOLD

#### Scenario: Bracket mode defers exits to the engine

- **WHEN** the strategy evaluates bars in `bracket` mode while a long position is open
- **THEN** it SHALL return HOLD regardless of where the close sits relative to the average

#### Scenario: Average types use their own price series

- **WHEN** the strategy evaluates the same bars with `average_type` sma, typical, and vwap
- **THEN** it SHALL compare the close against the mean of closes, the mean of typical
  prices, and the volume-weighted average of closes respectively

#### Scenario: Undefined measure holds

- **WHEN** the window has zero total volume with `average_type` vwap, or zero standard
  deviation with `distance` zscore
- **THEN** the strategy SHALL return HOLD rather than erroring

#### Scenario: Price above the average never shorts

- **WHEN** the strategy evaluates bars whose latest close is far above the rolling
  average and no position is open
- **THEN** it SHALL return HOLD and SHALL NOT open a short position

#### Scenario: Insufficient history holds

- **WHEN** the strategy is given fewer than `window` bars
- **THEN** it SHALL return HOLD rather than erroring

#### Scenario: Invalid parameters are rejected

- **WHEN** a session is created with an unknown `average_type`, `distance` or
  `exit_mode`, a `window` below 2, a negative threshold, or, in `revert` mode, an exit
  level not strictly above the entry level
- **THEN** the system SHALL reject the parameters with a validation error

#### Scenario: Catalog lists the Rolling-Average Reversion strategy

- **WHEN** a client requests the strategy catalog
- **THEN** the Rolling-Average Reversion strategy SHALL be included with its display
  name, explanation, required history, and parameter schema

### Requirement: Stopped-session summary

The system SHALL present a **session summary** for a stopped bot session (one whose
status is stopped, regardless of whether it stopped via the drawdown kill-switch or a
manual stop) and SHALL NOT present it for an active session. The summary SHALL report
how the finished session went and comprises (a) the **stop reason** and **stop time**,
(b) a **stats block**, and (c) a **cached AI-generated narrative**.

The stats block SHALL include: the session's **final value** and **total return** (as
both an amount and a fraction of allocated capital); the session's **peak value**
(high-water mark) and **maximum drawdown** (worst peak-to-trough drop); the session's
**lifespan** in days (from its start to its stop time) and its **number of closed
round-trip trades** and **win rate** (the share of closed round-trips with a positive
realized P&L); and the **best** and **worst** closed round-trip trade — each shown with
its **exact entry and exit** (entry price and time, exit price and time, and quantity) in
addition to ticker and realized P&L — and the session's **benchmark excess return**.
Figures that are unavailable (for example no closed round-trip, or no benchmark closes)
SHALL be reported as absent rather than fabricated.

The AI narrative SHALL be a short plain-language summary of the session's outcome,
generated by a tool-less AI agent from the summary's own stats and stop metadata. It
SHALL be generated **lazily on first request** for a stopped session and **persisted**
together with a **fingerprint of the inputs** it was generated from; a later request
SHALL reuse the persisted narrative when the fingerprint is unchanged and SHALL
regenerate it when the inputs (and therefore the fingerprint) change. If generation
fails, the summary SHALL still return its stats with the narrative reported as absent,
and a later request MAY retry generation.

#### Scenario: Summary shown only for a stopped session

- **WHEN** a client requests the session summary for a stopped bot session
- **THEN** the system SHALL return the summary (stop reason, stop time, stats block, and
  the AI narrative when available)

#### Scenario: No summary for an active session

- **WHEN** a client requests the session summary for an active bot session
- **THEN** the system SHALL report that no summary is available rather than returning
  summary statistics or invoking the AI agent

#### Scenario: Stats block content

- **WHEN** a client requests the summary for a stopped session that has at least one
  closed round-trip trade and a benchmark with usable closes
- **THEN** the stats block SHALL include the final value and total return (amount and
  fraction), peak value and maximum drawdown, lifespan in days, closed-trade count and
  win rate, the best and worst closed round-trip each with its entry price/time, exit
  price/time, quantity, ticker and realized P&L, and the benchmark excess return

#### Scenario: AI narrative generated once and cached

- **WHEN** a client requests the summary for a stopped session for the first time and the
  AI agent succeeds
- **THEN** the system SHALL persist the generated narrative with a fingerprint of its
  inputs, and a subsequent request with unchanged inputs SHALL return the persisted
  narrative without invoking the AI agent again

#### Scenario: AI narrative regenerated when inputs change

- **WHEN** a client requests the summary for a stopped session whose summarized inputs
  have changed since the narrative was last generated (the fingerprint no longer matches)
- **THEN** the system SHALL regenerate and re-persist the narrative

#### Scenario: AI narrative generation fails gracefully

- **WHEN** a client requests the summary for a stopped session and the AI agent fails or
  is unavailable
- **THEN** the system SHALL return the summary's stats with the narrative reported as
  absent rather than returning an error

### Requirement: Bot preset catalog

The system SHALL maintain a fixed catalog of **bot presets**. Each preset SHALL have a
stable key, a display name, a short description, a reference to the course algorithm it
reproduces, the key of the registered strategy it uses, that strategy's parameters, and
the risk controls it applies — the take-profit and stop-loss thresholds (each either a
percentage or off) and the drawdown kill-switch limit. A preset SHALL NOT fix the
session's capital, traded assets, benchmark, label, or position-sizing settings; those
remain choices made when a session is created. Every preset's strategy parameters SHALL be
valid for its strategy. Each registered strategy SHALL have exactly one **default
preset**. The system SHALL let a client list the presets, and the listing SHALL report,
for each preset, all of the fields above and whether it is its strategy's default.

The catalog SHALL include these presets, reproducing the reference-course recipes:

- **MA Crossover (Algo 6)** — default for the moving-average crossover strategy: fast
  period 5, slow period 12; take-profit 1%, stop-loss 2%, drawdown limit 5%.
- **RSI Mean Reversion (Algo 16)** — default for the RSI mean-reversion strategy:
  period 14, oversold 30, exit level 50; take-profit 0.5%, stop-loss 1%, drawdown
  limit 5%.
- **Turtle Breakout (Algo 25)** — default for the Donchian range-breakout strategy:
  Turtle version, entry period 20, exit period 10; take-profit off, stop-loss off,
  drawdown limit 5%.
- **Smart Range Breakout (Algo 8)** — Donchian range-breakout strategy, Locked version,
  channel period 20, ATR padding multiplier 0.5; take-profit 0.5%, stop-loss 2%,
  drawdown limit 5%.
- **SMA Band Reversion (Algo 5)** — default for the Rolling-Average Reversion strategy:
  SMA average, window 20, band distance, entry threshold 1%, exit threshold 0.5%, revert
  exit; take-profit off, stop-loss 2%, drawdown limit 5%.
- **Z-Score Reversion (Algo 4)** — Rolling-Average Reversion strategy: SMA average,
  window 20, z-score distance, entry z 1.0, exit z 0.2, revert exit; take-profit off,
  stop-loss 2%, drawdown limit 5%.
- **Mean Cross Reversion (Algo 14)** — Rolling-Average Reversion strategy: SMA average,
  window 60, band distance with entry threshold 0 (bare cross), bracket exit;
  take-profit 0.5%, stop-loss 1%, drawdown limit 5%.
- **VWAP Cross Reversion (Algo 39)** — Rolling-Average Reversion strategy: volume-weighted
  average, window 60, band distance with entry threshold 0 (bare cross), bracket exit;
  take-profit 0.5%, stop-loss 1%, drawdown limit 5%.

#### Scenario: List presets

- **WHEN** a client requests the preset catalog
- **THEN** the system SHALL return every preset with its key, display name, description,
  course reference, strategy key, strategy parameters, take-profit, stop-loss, drawdown
  limit, and whether it is its strategy's default

#### Scenario: One default preset per strategy

- **WHEN** a client requests the preset catalog
- **THEN** every registered strategy SHALL have exactly one preset marked as its default

#### Scenario: Preset parameters are valid for their strategy

- **WHEN** the preset catalog is loaded
- **THEN** every preset's strategy parameters SHALL validate against its strategy's
  parameter schema

#### Scenario: Rolling-Average Reversion course presets listed

- **WHEN** a client requests the preset catalog
- **THEN** it SHALL include the four Rolling-Average Reversion presets for Algos 5, 4, 14
  and 39, with the Algo 5 preset marked as the strategy's default

### Requirement: Preset-driven build form

The bot build form SHALL load its presets from the preset catalog rather than from
values fixed in the client. The form SHALL open preconfigured with the default preset of
the initially selected strategy. Selecting a different strategy SHALL apply that strategy's
default preset to the strategy parameters and risk controls; for the Donchian range-breakout
strategy, selecting a version SHALL apply the preset for that version. When the selected
strategy has more than one preset, the form SHALL offer a **preset selector** listing that
strategy's presets; choosing one SHALL apply it, and the selector SHALL show the applied
preset. Every applied value SHALL remain editable. When the user changes any value that
came from the applied preset, the form SHALL indicate that the configuration is
customized. Submitting the form SHALL send the applied preset's key together with the
configured values.

#### Scenario: Form opens with the default preset

- **WHEN** a user opens the build form
- **THEN** the strategy parameters and risk controls SHALL be filled from the default
  preset of the initially selected strategy

#### Scenario: Switching strategy applies its default preset

- **WHEN** a user selects a different strategy in the build form
- **THEN** the form SHALL apply that strategy's default preset to the strategy
  parameters and risk controls

#### Scenario: Switching Donchian version applies the version's preset

- **WHEN** a user selects a Donchian version in the build form
- **THEN** the form SHALL apply the preset for that version

#### Scenario: Choosing a preset from the selector applies it

- **WHEN** the selected strategy has more than one preset and the user chooses one of them
  in the preset selector
- **THEN** the form SHALL apply that preset to the strategy parameters and risk controls
  and show it as the applied preset

#### Scenario: Editing a preset value marks the configuration customized

- **WHEN** a user changes a strategy parameter or risk control that the applied preset set
- **THEN** the form SHALL indicate that the configuration is customized, and the field
  SHALL keep the user's value

### Requirement: Session provenance on the bot detail view

The bot detail view SHALL show where a session's configuration came from: the display
name of the preset it started from, marked as customized when its configuration was
changed from that preset, or an indication that it is a custom configuration when no preset
was used. When the session was deployed by a bot orchestrator, the detail view SHALL also
show that orchestrator's name as a link to the orchestrator's detail view.

#### Scenario: Unchanged preset session

- **WHEN** a user views a session that was created from a preset without changes
- **THEN** the detail view SHALL show that preset's display name without a customized mark

#### Scenario: Customized preset session

- **WHEN** a user views a session that was created from a preset and then changed
- **THEN** the detail view SHALL show that preset's display name marked as customized

#### Scenario: Session without a preset

- **WHEN** a user views a session that was created without a preset
- **THEN** the detail view SHALL show that the session uses a custom configuration

#### Scenario: Orchestrator-deployed session links its orchestrator

- **WHEN** a user views a session deployed by a bot orchestrator
- **THEN** the detail view SHALL show the orchestrator's name linking to its detail view

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

### Requirement: Tick outcome log

Every bot tick SHALL record its outcome: when it ran, whether the equity market was open, how
many bots were processed, skipped and failed, how many previously unrecorded orders were
reconciled, and — when the tick itself failed before completing — that it failed, with a
non-secret error message. A tick that finds the market closed SHALL still be recorded.
Recording the outcome SHALL NOT itself fail the tick, and an outcome SHALL be recorded even
when the tick fails. Outcomes older than 7 days SHALL be deleted by the daily bot snapshot job.

#### Scenario: Tick with a failing bot is recorded

- **WHEN** a tick processes one bot successfully and another bot fails
- **THEN** a tick outcome SHALL be recorded with one processed and one failed bot

#### Scenario: Market-closed tick is recorded

- **WHEN** a tick runs while the equity market is closed
- **THEN** a tick outcome SHALL be recorded marked as market closed

#### Scenario: Crashed tick is recorded

- **WHEN** a tick fails before completing
- **THEN** a tick outcome SHALL be recorded as failed with its error message

#### Scenario: Old outcomes are pruned

- **WHEN** the daily bot snapshot job runs
- **THEN** tick outcomes older than 7 days SHALL be deleted and newer ones kept

### Requirement: Per-bot failure state

When processing a bot during a tick fails, the system SHALL record on that bot when the failure
happened, a non-secret error message (for example the broker's rejection reason), and the number
of consecutive ticks in which it has failed. The next tick in which the bot is processed without
failing SHALL clear the failure state. A bot skipped for lack of fresh market data SHALL neither
set nor clear it. The failure state SHALL be part of the bot's read model.

#### Scenario: Failure is recorded and counted

- **WHEN** a bot fails in two consecutive ticks with a broker rejection
- **THEN** the bot SHALL report two consecutive failures, the time of the latest one and the
  rejection message

#### Scenario: Success clears the failure

- **WHEN** a failing bot is processed successfully in a later tick
- **THEN** its failure state SHALL be cleared

### Requirement: Bot failure banner

The bot detail view SHALL show a red banner while the bot has a recorded failure, stating how
many consecutive ticks have failed, when the latest failure happened and its error message. No
banner SHALL be shown for a bot without a recorded failure.

#### Scenario: Failing bot shows the banner

- **WHEN** the operator opens a bot that failed in its last three ticks
- **THEN** the page SHALL show a red banner with three consecutive failures, the latest failure
  time and the error

#### Scenario: Healthy bot shows no banner

- **WHEN** the operator opens a bot without a recorded failure
- **THEN** no failure banner SHALL be shown
