## MODIFIED Requirements

### Requirement: Dashboard aggregate performance tiles

The Dashboard SHALL present, for the active sessions currently selected in the equity curve, a point-in-time value band of **four** figures, marked as current/live and shown separately from the range-scoped performance tiles: the aggregate **current portfolio value** (the summed current value of the selected sessions), the aggregate **since-inception total return** as a percentage, the aggregate **since-inception lifetime profit/loss** as a dollar amount, and the aggregate **since-inception return versus benchmark** as an excess-return percentage. These four figures are point-in-time and SHALL reflect the current portfolio selection but SHALL NOT change with the range. The value band SHALL span the full page width and lay the four tiles out responsively (dividing the width on wide viewports, stacking on narrow ones).

The aggregate since-inception total return SHALL be the summed current value of the selected sessions minus their summed contributed capital, divided by their summed contributed capital, where a session's contributed capital is the sum of its capital contributions (opening capital plus any later capital increases). The aggregate lifetime profit/loss SHALL be the summed current value minus the summed contributed capital. The aggregate return versus benchmark SHALL be the aggregate since-inception total return minus the aggregate benchmark buy-and-hold return, where the benchmark leg sums, over the selected sessions, each session's since-inception buy-and-hold of its contributions in its **own** benchmark; when any selected session lacks a priceable benchmark value, the return-versus-benchmark tile SHALL show a clear "not yet available" state rather than a figure. The total return, lifetime profit/loss, and return-versus-benchmark figures SHALL be visually distinguished by sign (gain versus loss; outperformance versus underperformance).

The Dashboard SHALL also present range-scoped performance tiles showing, over the selected range, the summed realised profit/loss, the summed unrealised profit/loss, the money-weighted return, and the fees incurred within the range, grouped together under an indication of the active range. The summed realised and unrealised tiles SHALL use the per-session range-relative realised and unrealised profit/loss summed across the selected sessions, and SHALL be visually distinguished by sign (gain versus loss). The range-scoped tiles SHALL reflect the current portfolio selection and the selected range; the point-in-time value band SHALL reflect the current selection but SHALL NOT change with the range. The realised and unrealised figures are shown as two independent amounts and are not presented as an additive breakdown of the range return.

#### Scenario: Current value shown as point-in-time

- **WHEN** the Dashboard renders the aggregate performance tiles
- **THEN** the aggregate current portfolio value SHALL be shown in the point-in-time value band, separately from the range-scoped tiles, and marked as a current/live figure that does not change when the range changes

#### Scenario: Value band presents four point-in-time figures

- **WHEN** the Dashboard renders the point-in-time value band for the selected sessions
- **THEN** it SHALL present four live tiles — aggregate current value, aggregate since-inception total return percentage, aggregate since-inception lifetime profit/loss amount, and aggregate since-inception return versus benchmark — spanning the full page width

#### Scenario: Value-band figures are range-independent

- **WHEN** a user changes the range
- **THEN** the four point-in-time value-band figures SHALL NOT change, while the range-scoped tiles recompute for the new range

#### Scenario: Value-band figures reflect the selection

- **WHEN** a user changes the set of selected portfolios
- **THEN** the aggregate current value, total return, lifetime profit/loss, and return versus benchmark SHALL recompute over the newly selected sessions from already-fetched data without a new request

#### Scenario: Since-inception figures distinguished by sign

- **WHEN** the aggregate since-inception total return, lifetime profit/loss, or return versus benchmark for the selected sessions is positive or negative
- **THEN** the corresponding tile SHALL indicate the sign visually (gain versus loss; outperformance versus underperformance)

#### Scenario: Return versus benchmark unavailable

- **WHEN** any selected session has no priceable since-inception benchmark value
- **THEN** the return-versus-benchmark tile SHALL show a clear "not yet available" state rather than a figure

#### Scenario: Tiles reflect range and selection

- **WHEN** a user changes the range or the set of selected portfolios
- **THEN** the range-scoped tiles SHALL recompute to show summed range realised P&L, summed range unrealised P&L, money-weighted range return, and range fees for the selected sessions, grouped under an indication of the active range

#### Scenario: Realised and unrealised tiles distinguished by sign

- **WHEN** the summed range realised or unrealised profit/loss for the selected sessions is positive or negative
- **THEN** the corresponding tile SHALL indicate the sign visually (gain versus loss)
