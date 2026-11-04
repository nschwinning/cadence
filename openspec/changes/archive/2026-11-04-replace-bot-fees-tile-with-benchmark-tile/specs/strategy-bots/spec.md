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

## ADDED Requirements

### Requirement: Bot detail performance tiles

The bot detail view's performance section SHALL present the session's KPIs as tiles,
including a **benchmark-comparison tile** that shows the session's excess return as its
primary figure and the benchmark's own return as a secondary figure, labelled with the
benchmark's display name. The performance section SHALL NOT present a transaction-fees
tile.

When the benchmark comparison is unavailable (the session has no snapshot yet or the
benchmark lacks usable closes), the benchmark-comparison tile SHALL render a neutral
placeholder in place of the figures rather than an error.

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
