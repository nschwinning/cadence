## MODIFIED Requirements

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
