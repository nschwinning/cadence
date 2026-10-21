## MODIFIED Requirements

### Requirement: Dashboard combined equity curve

The Dashboard SHALL present a combined equity curve as a single line equal to the summed value of the selected active sessions over the selected range, on a common date axis. A session SHALL contribute zero before its first recorded value (carry-forward thereafter). The Dashboard SHALL offer a selectable list of the active sessions, all selected by default, letting the user include or exclude each session; the selection SHALL also drive the hero tiles and the leaderboard. Toggling a session SHALL re-aggregate from already-fetched per-session data without issuing a new request per toggle. When no session is selected, the chart SHALL show an empty state instead of a line.

The chart SHALL also overlay **benchmark index lines** on the same dollar axis. It SHALL present a benchmark legend listing every index in the benchmark catalog, each individually selectable, with the S&P 500 selected by default and the others deselected. For each selected benchmark that has price data over the range, the chart SHALL draw a line equal to the **sum over the selected sessions of a buy-and-hold of each session's contributed capital in that index** — for each selected session, its opening capital is treated as invested in the index on the session's first date and each later capital increase as invested on its effective date, each held thereafter and valued forward by the index's price movement, and these per-session positions are summed on the common date axis. Consequently the benchmark line starts from zero before any selected session has opened and **steps up as each selected session opens** (and on each later capital increase), mirroring how the combined equity line aggregates, so the two curves are directly comparable in USD (no percent/dollar toggle). A selected benchmark that has no price data over the range SHALL draw no line, and its legend control SHALL be inert rather than erroring. Benchmark lines SHALL be visually distinguishable from the portfolio line and from one another. Toggling a benchmark SHALL add or remove its line without issuing a new request, and changing the session selection SHALL re-aggregate the benchmark lines over the newly selected sessions. When no session is selected, no benchmark lines SHALL be drawn (the empty state is shown instead).

When the equity curve plots a line, it SHALL support **hover inspection**: moving the pointer over the plot area SHALL identify the plotted point nearest the pointer's horizontal position and SHALL show a tooltip reporting that point's **date**, the **summed equity value** in USD at that point, and the aggregated USD value of each currently-drawn benchmark line at that point. The tooltip SHALL be rendered legibly (not distorted by the chart's scaling) and SHALL be positioned near the hovered point without being clipped out of the chart area. The chart MAY also mark the hovered point visually. When the pointer leaves the plot area, the tooltip SHALL be dismissed. Hover inspection SHALL NOT change any plotted value and SHALL NOT appear when the empty state is shown.

#### Scenario: Summed line over selected sessions

- **WHEN** the Dashboard renders the equity curve with one or more sessions selected
- **THEN** it SHALL plot a single line equal to the sum of the selected sessions' values across the range, each session contributing zero before its first recorded value

#### Scenario: Toggling a session re-aggregates without refetch

- **WHEN** a user includes or excludes a session in the equity curve
- **THEN** the line, hero tiles, and leaderboard SHALL recompute from already-fetched data without a new request per toggle

#### Scenario: Benchmark legend defaults to S&P 500

- **WHEN** the Dashboard first renders the equity curve
- **THEN** it SHALL list every catalog benchmark in the legend with only the S&P 500 selected, and draw the S&P 500 line as the sum over the selected sessions of a buy-and-hold of each session's contributed capital in the S&P 500, stepping up as each selected session opens, alongside the portfolio line

#### Scenario: Toggling a benchmark adds or removes its line without refetch

- **WHEN** a user selects or deselects a benchmark in the legend
- **THEN** the chart SHALL add or remove that index's aggregated line using already-fetched data, without issuing a new request

#### Scenario: Benchmark lines re-rebase when the session selection changes

- **WHEN** a user changes which sessions are selected
- **THEN** each drawn benchmark line SHALL re-aggregate over the newly selected sessions, so excluding a session removes its contributed capital from the benchmark line just as it is removed from the equity line

#### Scenario: Benchmark without data over the range

- **WHEN** a selected benchmark has no price data over the selected range
- **THEN** the chart SHALL draw no line for it and its legend control SHALL be inert rather than erroring

#### Scenario: Hover reveals the summed value and date

- **WHEN** a user moves the pointer over the rendered combined equity curve
- **THEN** the view SHALL show a tooltip reporting the nearest point's date, the summed equity value in USD, and the aggregated USD value of each currently-drawn benchmark line at that point

#### Scenario: Tooltip dismisses on leave

- **WHEN** the pointer leaves the equity curve's plot area
- **THEN** the view SHALL dismiss the hover tooltip

#### Scenario: No sessions selected

- **WHEN** no session is selected
- **THEN** the equity curve SHALL show an empty state rather than a line, and SHALL draw no benchmark lines
