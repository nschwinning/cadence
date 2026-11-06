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
is the one with the lowest; each SHALL be reported with its ticker and realized P&L. When
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
- **THEN** the returned KPIs SHALL include the best closed round-trip (its ticker and
  realized P&L) and the worst closed round-trip (its ticker and realized P&L)

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
