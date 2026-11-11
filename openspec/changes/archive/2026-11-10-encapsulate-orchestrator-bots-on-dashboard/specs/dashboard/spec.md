## MODIFIED Requirements

### Requirement: Range-scoped dashboard overview

The system SHALL provide a single endpoint returning an aggregated overview of the system scoped to a selected time range, where the range is one of `1D`, `1W`, `1M`, `YTD`, `1Y`, or `Max`. The overview SHALL aggregate over active paper-trading sessions, active **manually created** strategy-bot sessions, and active **bot orchestrators** together. A strategy bot deployed by an orchestrator SHALL NOT be aggregated on its own; it is represented only through its orchestrator, so the orchestrator's free capital and its bots are counted exactly once. It SHALL return, for the selected range, per-session performance data, an automation summary, a recent-activity list, a universe-balance summary, and universe performers. This overview SHALL be provided in addition to the existing aggregated dashboard metrics, which remain unchanged. When no active sessions or assets exist, the overview SHALL return empty collections and zeroed aggregates rather than an error.

#### Scenario: Fetch the overview for a range

- **WHEN** a client requests the dashboard overview for a given range
- **THEN** the system SHALL return the per-session performance data, automation summary, recent activity, universe balance, and universe performers computed for that range over the active sessions

#### Scenario: Overview includes active bot sessions

- **WHEN** a client requests the dashboard overview and active strategy-bot sessions exist
- **THEN** the returned per-session performance data SHALL include the active bot sessions alongside the active AI paper-trading sessions, computed for the selected range

#### Scenario: Unsupported range value

- **WHEN** a client requests the overview with a range outside the supported set
- **THEN** the system SHALL reject the request rather than silently defaulting

#### Scenario: Empty system

- **WHEN** there are no active sessions and no assets
- **THEN** the system SHALL return empty collections and zeroed aggregates rather than an error

#### Scenario: Orchestrator bots are represented by their orchestrator

- **WHEN** a client requests the dashboard overview while an active orchestrator has deployed
  two active bots
- **THEN** the overview SHALL include one row for the orchestrator and SHALL NOT include
  separate rows for its two bots

### Requirement: Per-session performance data for the overview

For each active session the overview SHALL return the data needed to render aggregate performance, compare sessions, and compute per-session benchmark comparison lines over the selected range, without requiring the client to re-fetch when it changes which sessions are included. For each session this SHALL include a stable identifier, a display label, a `kind` discriminator identifying the session as an AI paper-trading session, a strategy bot, or a bot orchestrator, the allocated capital, the current value, the profit/loss and fees attributable to the selected range, the realised and unrealised profit/loss attributable to the selected range, a value series over the range suitable for plotting, the session's capital contributions — the session's opening capital effective at its start date plus any later capital-increase events, each a contribution amount and the date it became effective — and a since-inception benchmark buy-and-hold current value. The value series SHALL be windowed to the selected range; a session that has no value before the range start SHALL be represented as contributing zero until its first recorded value. AI sessions, strategy-bot sessions and bot orchestrators SHALL be returned in this same shape, distinguished only by the `kind` discriminator.

Each session's reported **current value** (and the unrealised profit/loss reported alongside it) SHALL be the session's live, most-recent value on a per-kind basis, so that both kinds are live on the same basis: for an **AI paper-trading** session it SHALL be the session's open positions marked to market against current quotes; for a **strategy-bot** session it SHALL be the session's most recently captured value observation — the latest intraday value point when it is more recent than the latest daily snapshot, otherwise the latest daily snapshot, otherwise cash plus open positions valued at cost when the session has neither (with a zero unrealised baseline in that cost-marked case). A bot session's reported current value SHALL therefore match the live current value already exposed by the per-bot current-value read rather than being pinned to its latest daily snapshot. No live broker or quote call SHALL be made to value a bot session. For a **bot orchestrator** the current value SHALL be its free capital plus the current value of each of its bots whose capital has not yet been returned — the same figure as the orchestrator's own value read — and its unrealised profit/loss SHALL be the sum of its active bots' unrealised profit/loss; no live broker or quote call SHALL be made to value it.

An orchestrator row SHALL use the orchestrator's **capital pool** as its allocated capital and as its **single opening contribution**, effective at its first daily snapshot date (or the current date before any snapshot); capital it recycles between its bots SHALL NOT be reported as new contributions. Its value series SHALL come from the orchestrator's daily snapshots, windowed to the range, with a single current-value point before the first snapshot exists; its range profit/loss SHALL be measured against its latest snapshot on or before the range start, or against the capital pool when there is none; its realised profit/loss and fees attributable to the range SHALL be the sums over all of its bots; and its since-inception benchmark buy-and-hold value SHALL value the capital pool in the orchestrator's benchmark on the same basis as AI sessions.

The session's **range realised profit/loss** SHALL be the sum of the realised profit/loss of the closed positions whose close falls within the selected range; for the maximum range this SHALL equal the session's cumulative realised profit/loss. The session's **range unrealised profit/loss** SHALL be the session's current live unrealised profit/loss on its open positions (valued at current market quotes) minus the unrealised profit/loss recorded in the session's daily value snapshot at the start of the range; when the session has no value snapshot at or before the range start — including the maximum range — the range-start unrealised baseline SHALL be zero, so the figure equals the current live unrealised profit/loss. The realised figure SHALL be gross of fees, and the realised and unrealised figures SHALL be returned as two independent amounts rather than as an additive decomposition of the range profit/loss.

The session's **since-inception benchmark value** SHALL be the current USD value of a contribution-aware buy-and-hold of the session's capital contributions in the session's own benchmark, computed on the same basis as the dashboard's combined-equity benchmark overlay: each contribution is treated as invested in the benchmark index at the index's close on the contribution's effective date and held thereafter, and the resulting position is valued at the index's latest available close. This money-weighted basis matches the money-weighted total-return figure the client derives, so the two are comparable. This figure is point-in-time and range-independent (the full benchmark history is used, not a range-windowed slice). When the session's benchmark has no priceable close for its contributions, the since-inception benchmark value SHALL be returned as null so the client can treat the comparison as unavailable rather than reporting a misleading excess.

#### Scenario: Session series windowed to the range

- **WHEN** the overview is requested for a range
- **THEN** each active session's returned value series SHALL cover the selected range and the session SHALL contribute zero for dates before its first recorded value

#### Scenario: Each row carries a kind discriminator

- **WHEN** the overview is requested
- **THEN** each returned session row SHALL carry a `kind` discriminator identifying it as an AI paper-trading session or a strategy bot, and bot rows SHALL be returned in the same shape as AI rows

#### Scenario: Range-relative profit/loss and fees

- **WHEN** the overview is requested for a range
- **THEN** each session's returned profit/loss SHALL be its value at the end of the range minus its value at the start of the range, and its fees SHALL be those incurred within the range

#### Scenario: Range-relative realised and unrealised profit/loss

- **WHEN** the overview is requested for a range
- **THEN** each session's returned realised profit/loss SHALL be the sum of its closed positions' realised profit/loss for lots closed within the range, and its returned unrealised profit/loss SHALL be its current live unrealised profit/loss minus the unrealised profit/loss recorded in its range-start value snapshot (or minus zero when it has no snapshot at the range start)

#### Scenario: Maximum range reduces realised and unrealised to cumulative

- **WHEN** the overview is requested for the maximum range
- **THEN** each session's returned realised profit/loss SHALL equal its cumulative closed-lot realised profit/loss and its returned unrealised profit/loss SHALL equal its current live unrealised profit/loss on open positions

#### Scenario: Bot current value reflects the freshest observation

- **WHEN** the overview is requested and an active strategy-bot session has a latest intraday value point more recent than its latest daily snapshot
- **THEN** that bot row's returned current value and unrealised profit/loss SHALL be taken from that intraday value point rather than from the latest daily snapshot, so the bot row is live on the same basis as AI rows; and when the bot has only daily snapshots its current value SHALL be the latest snapshot, and when it has neither it SHALL be cash plus open positions valued at cost with a zero unrealised baseline

#### Scenario: Session capital contributions included

- **WHEN** the overview is requested
- **THEN** each session's returned data SHALL include its capital contributions — its opening capital with the date it became effective and any later capital-increase amounts each with their effective date — so a client can compute a buy-and-hold benchmark comparison for that session

#### Scenario: Since-inception benchmark value included

- **WHEN** the overview is requested and a session's benchmark has priceable closes for its contributions
- **THEN** the session's returned data SHALL include a since-inception benchmark buy-and-hold current value equal to the current USD value of its contributions invested in its own benchmark on each contribution's effective date and held, so a client can aggregate an excess-return comparison across the selected sessions

#### Scenario: Since-inception benchmark value unavailable

- **WHEN** the overview is requested and a session's benchmark has no priceable close for its contributions
- **THEN** the session's since-inception benchmark value SHALL be returned as null

#### Scenario: Orchestrator row in the shared shape

- **WHEN** the overview is requested with an active orchestrator whose capital pool is $10,000,
  with $6,700 free and one bot currently worth $3,350
- **THEN** the orchestrator row SHALL carry the `kind` orchestrator, an allocated capital and
  single opening contribution of $10,000, and a current value of $10,050

#### Scenario: Recycled capital is not a new contribution

- **WHEN** an orchestrator stops a bot and deploys another one with the returned capital
- **THEN** the orchestrator row's contributions SHALL still be its single opening
  contribution of the capital pool
