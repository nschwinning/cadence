## MODIFIED Requirements

### Requirement: Per-session performance data for the overview

For each active session the overview SHALL return the data needed to render aggregate performance, compare sessions, and compute per-session benchmark comparison lines over the selected range, without requiring the client to re-fetch when it changes which sessions are included. For each session this SHALL include a stable identifier, a display label, the allocated capital, the current value, the profit/loss and fees attributable to the selected range, the realised and unrealised profit/loss attributable to the selected range, a value series over the range suitable for plotting, the session's capital contributions — the session's opening capital effective at its start date plus any later capital-increase events, each a contribution amount and the date it became effective — and a since-inception benchmark buy-and-hold current value. The value series SHALL be windowed to the selected range; a session that has no value before the range start SHALL be represented as contributing zero until its first recorded value.

The session's **range realised profit/loss** SHALL be the sum of the realised profit/loss of the closed positions whose close falls within the selected range; for the maximum range this SHALL equal the session's cumulative realised profit/loss. The session's **range unrealised profit/loss** SHALL be the session's current live unrealised profit/loss on its open positions (valued at current market quotes) minus the unrealised profit/loss recorded in the session's daily value snapshot at the start of the range; when the session has no value snapshot at or before the range start — including the maximum range — the range-start unrealised baseline SHALL be zero, so the figure equals the current live unrealised profit/loss. The realised figure SHALL be gross of fees, and the realised and unrealised figures SHALL be returned as two independent amounts rather than as an additive decomposition of the range profit/loss.

The session's **since-inception benchmark value** SHALL be the current USD value of a contribution-aware buy-and-hold of the session's capital contributions in the session's own benchmark, computed on the same basis as the dashboard's combined-equity benchmark overlay: each contribution is treated as invested in the benchmark index at the index's close on the contribution's effective date and held thereafter, and the resulting position is valued at the index's latest available close. This money-weighted basis matches the money-weighted total-return figure the client derives, so the two are comparable. This figure is point-in-time and range-independent (the full benchmark history is used, not a range-windowed slice). When the session's benchmark has no priceable close for its contributions, the since-inception benchmark value SHALL be returned as null so the client can treat the comparison as unavailable rather than reporting a misleading excess.

#### Scenario: Session series windowed to the range

- **WHEN** the overview is requested for a range
- **THEN** each active session's returned value series SHALL cover the selected range and the session SHALL contribute zero for dates before its first recorded value

#### Scenario: Range-relative profit/loss and fees

- **WHEN** the overview is requested for a range
- **THEN** each session's returned profit/loss SHALL be its value at the end of the range minus its value at the start of the range, and its fees SHALL be those incurred within the range

#### Scenario: Range-relative realised and unrealised profit/loss

- **WHEN** the overview is requested for a range
- **THEN** each session's returned realised profit/loss SHALL be the sum of its closed positions' realised profit/loss for lots closed within the range, and its returned unrealised profit/loss SHALL be its current live unrealised profit/loss minus the unrealised profit/loss recorded in its range-start value snapshot (or minus zero when it has no snapshot at the range start)

#### Scenario: Maximum range reduces realised and unrealised to cumulative

- **WHEN** the overview is requested for the maximum range
- **THEN** each session's returned realised profit/loss SHALL equal its cumulative closed-lot realised profit/loss and its returned unrealised profit/loss SHALL equal its current live unrealised profit/loss on open positions

#### Scenario: Session capital contributions included

- **WHEN** the overview is requested
- **THEN** each session's returned data SHALL include its capital contributions — its opening capital with the date it became effective and any later capital-increase amounts each with their effective date — so a client can compute a buy-and-hold benchmark comparison for that session

#### Scenario: Since-inception benchmark value included

- **WHEN** the overview is requested and a session's benchmark has priceable closes for its contributions
- **THEN** the session's returned data SHALL include a since-inception benchmark buy-and-hold current value equal to the current USD value of its contributions invested in its own benchmark on each contribution's effective date and held, so a client can aggregate an excess-return comparison across the selected sessions

#### Scenario: Since-inception benchmark value unavailable

- **WHEN** the overview is requested and a session's benchmark has no priceable close for its contributions
- **THEN** the session's since-inception benchmark value SHALL be returned as null
