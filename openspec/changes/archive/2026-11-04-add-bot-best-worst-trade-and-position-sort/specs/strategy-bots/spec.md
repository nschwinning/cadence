## MODIFIED Requirements

### Requirement: Bot value snapshots and performance KPIs

The system SHALL record a daily value snapshot for each active bot session capturing
its total value — **cash plus the marked-to-market value of all open positions** — and
realised and unrealised profit/loss aggregated across the session's positions, and SHALL
expose per-session KPIs computed from the ledger and snapshots (for example current
value, **available (free, uninvested) cash**, total return, realised/unrealised
profit/loss, and the session's **best and worst closed round-trip trade**). These SHALL
be computed within the strategy-bots subsystem and SHALL NOT depend on the paper-trading
subsystem's persistence.

A closed round-trip trade is an entry (buy) paired with the exit (sell) that fully closes
that position; its realized P&L is the exit proceeds minus the entry cost (net of fees).
The **best** closed round-trip is the one with the highest realized P&L and the **worst**
is the one with the lowest; each SHALL be reported with its ticker and realized P&L. When
the session has no closed round-trip yet (no completed exit), the best and worst trade
SHALL be reported as absent.

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

## ADDED Requirements

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
