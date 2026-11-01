## MODIFIED Requirements

### Requirement: Session value history chart

The paper-trading session view SHALL render a line chart of the session's total
portfolio value over time from its daily value-history snapshots, and SHALL overlay
on the same chart a second line for the session's benchmark — a buy-and-hold of the
session's allocated capital in the benchmark, rebased to start equal to the session's
value — so the two curves can be compared directly. When the benchmark value is
unavailable for the session's history, the view SHALL render the portfolio-value line
alone without error. When the session has fewer than two snapshots the view SHALL show
a placeholder indicating there is not yet enough history to chart, rather than a broken
or empty chart. While the value history is loading or fails to load, the view SHALL show
a loading or error state consistent with the page's other panels.

The chart SHALL **carry each line's last recorded value forward** across dates on
which the session has no snapshot — weekends and any other non-trading days — so the
plotted value on such a date equals the most recent snapshot on or before it, drawn as
a flat segment rather than a sloped line or a gap. The plotted axis SHALL extend to a
trailing horizon of the current day (US Eastern), so the latest weekend or other
non-trading day reads flat at the preceding trading day's value rather than ending the
line at the last stored snapshot. No value before a line's first snapshot SHALL be
synthesized. Carrying values forward SHALL NOT alter any stored snapshot; it only
affects what the chart draws.

When the chart is rendered, it SHALL display a **labelled x-axis** marking several
calendar dates spread across the plotted history — more than just the first and last
points — and a **labelled y-axis** marking portfolio value in USD, so a user can read
what any point on a line represents. Axis tick labels SHALL be rendered legibly (not
distorted by the chart's scaling). The chart SHALL also show a **legend** identifying
which line is the session's portfolio value and which line is the benchmark; when the
benchmark line is not drawn, the legend SHALL not imply a benchmark line is present.

The value history chart SHALL display an **end-of-day indicator** (for example, an "End
of day" badge beside the chart heading) communicating that the chart reflects end-of-day
value snapshots and that its latest point is the most recent snapshot (the prior close),
together with a brief explanatory hint that it can lag the live performance tiles
intraday. The indicator SHALL NOT change any plotted value.

When the chart is rendered with plottable history, it SHALL support **hover
inspection**: moving the pointer over the plot area SHALL identify the plotted snapshot
nearest the pointer's horizontal position and SHALL show a tooltip reporting that
snapshot's **date** and its **portfolio value** in USD, and — when a benchmark value
exists at that snapshot — the **benchmark value** in USD. The tooltip SHALL be rendered
legibly (not distorted by the chart's scaling) and SHALL be positioned near the hovered
point without being clipped out of the chart area. The chart MAY also mark the hovered
point visually (for example, a crosshair or dot). When the pointer leaves the plot area,
the tooltip SHALL be dismissed. Hover inspection SHALL NOT change any plotted value and
SHALL NOT appear when the placeholder, loading, or error state is shown.

#### Scenario: Chart renders with history

- **WHEN** a user opens a session that has at least two value snapshots
- **THEN** the view SHALL render a line chart of the session's total value over time

#### Scenario: Value carried forward over non-trading days

- **WHEN** an equity-only session's latest snapshot is a prior trading day and the current day is a weekend or other non-trading day
- **THEN** the view SHALL draw the value line flat from that snapshot forward to the current day at the same value, rather than ending the line at the last snapshot

#### Scenario: Chart marked as end-of-day

- **WHEN** a user views the session value history chart
- **THEN** the view SHALL show an end-of-day indicator on the chart communicating that it reflects end-of-day snapshots, with a brief hint that it can lag the live performance tiles intraday

#### Scenario: Benchmark overlaid on the chart

- **WHEN** a user opens a session whose value history includes benchmark values
- **THEN** the view SHALL overlay the benchmark line on the value chart alongside the session's total-value line

#### Scenario: Benchmark unavailable

- **WHEN** a session's value history has no benchmark values
- **THEN** the view SHALL render the session's total-value line alone without error

#### Scenario: Axes are labelled

- **WHEN** the value chart is rendered with enough history to plot
- **THEN** the view SHALL show several dated x-axis labels spread across the history — more than just the endpoints — and USD y-axis labels around the plot area

#### Scenario: Legend identifies each line

- **WHEN** the value chart is rendered
- **THEN** the view SHALL show a legend naming the portfolio-value line and, when it is drawn, the benchmark line, each keyed to its line's colour or style

#### Scenario: Hover reveals a snapshot's value and date

- **WHEN** a user moves the pointer over the rendered value chart
- **THEN** the view SHALL show a tooltip reporting the nearest snapshot's date and its portfolio value in USD, and the benchmark value in USD when a benchmark value exists at that snapshot

#### Scenario: Tooltip dismisses on leave

- **WHEN** the pointer leaves the value chart's plot area
- **THEN** the view SHALL dismiss the hover tooltip

#### Scenario: Not enough history

- **WHEN** a user opens a session that has fewer than two value snapshots
- **THEN** the view SHALL show a placeholder indicating there is not yet enough
  history to chart

#### Scenario: Loading and error states

- **WHEN** the session's value history is loading or fails to load
- **THEN** the view SHALL show a loading or error state instead of the chart

### Requirement: Paper-trading session comparison chart

The paper-trading session list view SHALL display a **performance-comparison chart** that overlays every non-archived session (active, paused, stopped) on a shared time axis, so a user can compare sessions and see which performs best. The chart SHALL plot one line per session that has at least two value points, sharing a single y-scale across all plotted lines, and SHALL show a **legend** mapping each line's color to its session label. The chart's lines and its legend SHALL be ordered by session creation date, oldest first, and each session's color SHALL be keyed to the session's stable identity so a given session keeps the same color across renders. Sessions with fewer than two value points SHALL appear in the legend but SHALL NOT be plotted. The chart SHALL offer a **metric toggle** with two views, defaulting to the return view:

- **Return %** (default): each session's line SHALL be its cumulative total-return percentage, computed from the session's total value relative to its allocated capital, so sessions with different allocated capital and start dates are compared fairly and the highest line is the best performer.
- **Value ($)**: each session's line SHALL be its absolute total portfolio value in USD.

Each plotted session's line SHALL **carry its last recorded value forward** across dates on which that session has no value point — weekends and any other non-trading days — so the line is drawn flat at the preceding trading day's value rather than ending early or sloping across the gap. The chart's shared time axis SHALL span the union of all plotted sessions' dates extended to a trailing horizon of the current day (US Eastern), so that a session whose latest point is an earlier trading day (for example an equity-only session with no weekend snapshots) stays plotted — flat — alongside sessions that do have more recent points (for example sessions holding crypto, which is valued on weekends). No value before a session's first value point SHALL be synthesized, and a session with fewer than two value points SHALL remain legended-but-not-plotted. Carrying values forward SHALL affect only what the chart draws, not any stored data.

When the chart plots at least one line, it SHALL display a **labelled x-axis** marking several calendar dates spread across the shared time axis — more than just the first and last points — and a **labelled y-axis** whose tick labels match the active metric — percentages in the Return % view and USD amounts in the Value $ view — and the y-axis labels SHALL update when the metric toggle switches. Axis tick labels SHALL be rendered legibly (not distorted by the chart's scaling).

When the chart plots at least one line, it SHALL support **hover inspection**: moving the pointer over the plot area SHALL identify the plotted point nearest the pointer across all plotted session lines and SHALL show a tooltip reporting that point's **session label**, its **date**, and its **value** formatted for the active metric — a percentage in the Return % view and a USD amount in the Value $ view. The tooltip SHALL be rendered legibly (not distorted by the chart's scaling) and SHALL be positioned near the hovered point without being clipped out of the chart area. The chart MAY also mark the hovered point visually. When the pointer leaves the plot area, the tooltip SHALL be dismissed. Hover inspection SHALL NOT change any plotted value and SHALL NOT appear when the insufficient-data placeholder, loading, or error state is shown.

When no non-archived session has enough value points to plot, the chart SHALL show an insufficient-data placeholder rather than an empty plot area. The chart SHALL show its own loading and error states while the comparison data is being fetched or if the fetch fails.

#### Scenario: Comparison chart overlays non-archived sessions

- **WHEN** a user opens the paper-trading session list and multiple non-archived sessions each have at least two value points
- **THEN** the chart SHALL render one line per such session on a shared y-scale with a legend identifying each session by its label

#### Scenario: Equity-only session stays plotted flat over a weekend

- **WHEN** one plotted session's latest value point is a Friday (an equity-only session with no weekend snapshots) while another plotted session has later weekend value points
- **THEN** the chart SHALL extend the equity-only session's line flat from Friday across the weekend at its Friday value, so it remains visible and comparable rather than ending at Friday

#### Scenario: Lines and legend are ordered oldest-created first

- **WHEN** the comparison chart renders lines for several sessions
- **THEN** the chart's lines and its legend SHALL be ordered by session creation date, oldest first

#### Scenario: Toggle between return % and absolute value

- **WHEN** a user switches the metric toggle from the default return view to the value view
- **THEN** the chart SHALL re-plot each session's line as its absolute portfolio value in USD, and switching back SHALL re-plot cumulative total-return percentage

#### Scenario: Return view is the default

- **WHEN** the comparison chart first renders
- **THEN** it SHALL show the cumulative total-return percentage view by default

#### Scenario: Axes are labelled and track the metric

- **WHEN** the comparison chart plots at least one line
- **THEN** the view SHALL show several dated x-axis labels spread across the time axis — more than just the endpoints — and y-axis labels formatted as percentages in the Return % view and as USD amounts in the Value $ view, and the y-axis labels SHALL change when the metric toggle is switched

#### Scenario: Hover reveals the nearest series point

- **WHEN** a user moves the pointer over the rendered comparison chart
- **THEN** the view SHALL show a tooltip reporting the nearest plotted point's session label, its date, and its value formatted as a percentage in the Return % view or a USD amount in the Value $ view

#### Scenario: Tooltip value tracks the metric toggle

- **WHEN** a user hovers the comparison chart and then switches the metric toggle
- **THEN** the hover tooltip's value SHALL be formatted for the active metric — a percentage in the Return % view and a USD amount in the Value $ view

#### Scenario: Tooltip dismisses on leave

- **WHEN** the pointer leaves the comparison chart's plot area
- **THEN** the view SHALL dismiss the hover tooltip

#### Scenario: Session with too little history is legended but not plotted

- **WHEN** a non-archived session has fewer than two value points
- **THEN** that session SHALL appear in the legend but SHALL NOT be drawn as a line

#### Scenario: Insufficient data placeholder

- **WHEN** no non-archived session has at least two value points
- **THEN** the chart SHALL display an insufficient-data placeholder instead of an empty plot

#### Scenario: Loading and error states

- **WHEN** the comparison data is loading, or the request fails
- **THEN** the chart SHALL show a loading indicator while pending and an error state on failure, rather than a blank or broken chart

### Requirement: Dashboard combined equity curve

The Dashboard SHALL present a combined equity curve as a single line equal to the summed value of the selected active sessions over the selected range, on a common date axis. A session SHALL contribute zero before its first recorded value (carry-forward thereafter). The common date axis SHALL span the union of the selected sessions' snapshot dates extended to a trailing horizon of the current day (US Eastern), so the combined line — and the benchmark lines described below — extend flat across trailing non-trading days (for example the current weekend) at their last known value rather than ending at the latest snapshot date. The Dashboard SHALL offer a selectable list of the active sessions, all selected by default, letting the user include or exclude each session; the selection SHALL also drive the hero tiles and the leaderboard. Toggling a session SHALL re-aggregate from already-fetched per-session data without issuing a new request per toggle. When no session is selected, the chart SHALL show an empty state instead of a line.

The chart SHALL also overlay **benchmark index lines** on the same dollar axis. It SHALL present a benchmark legend listing every index in the benchmark catalog, each individually selectable, with the S&P 500 selected by default and the others deselected. For each selected benchmark that has price data over the range, the chart SHALL draw a line equal to the **sum over the selected sessions of a buy-and-hold of each session's contributed capital in that index** — for each selected session, its opening capital is treated as invested in the index on the session's first date and each later capital increase as invested on its effective date, each held thereafter and valued forward by the index's price movement, and these per-session positions are summed on the common date axis. Each benchmark line's value on a date SHALL use the index's last close on or before that date, so the line carries forward flat across dates the index did not trade. Consequently the benchmark line starts from zero before any selected session has opened and **steps up as each selected session opens** (and on each later capital increase), mirroring how the combined equity line aggregates, so the two curves are directly comparable in USD (no percent/dollar toggle). A selected benchmark that has no price data over the range SHALL draw no line, and its legend control SHALL be inert rather than erroring. Benchmark lines SHALL be visually distinguishable from the portfolio line and from one another. Toggling a benchmark SHALL add or remove its line without issuing a new request, and changing the session selection SHALL re-aggregate the benchmark lines over the newly selected sessions. When no session is selected, no benchmark lines SHALL be drawn (the empty state is shown instead).

When the equity curve plots a line, it SHALL support **hover inspection**: moving the pointer over the plot area SHALL identify the plotted point nearest the pointer's horizontal position and SHALL show a tooltip reporting that point's **date**, the **summed equity value** in USD at that point, and the aggregated USD value of each currently-drawn benchmark line at that point. The tooltip SHALL be rendered legibly (not distorted by the chart's scaling) and SHALL be positioned near the hovered point without being clipped out of the chart area. The chart MAY also mark the hovered point visually. When the pointer leaves the plot area, the tooltip SHALL be dismissed. Hover inspection SHALL NOT change any plotted value and SHALL NOT appear when the empty state is shown.

#### Scenario: Summed line over selected sessions

- **WHEN** the Dashboard renders the equity curve with one or more sessions selected
- **THEN** it SHALL plot a single line equal to the sum of the selected sessions' values across the range, each session contributing zero before its first recorded value

#### Scenario: Combined line extends flat over a trailing weekend

- **WHEN** the latest snapshot among the selected sessions is a prior trading day and the current day is a weekend or other non-trading day
- **THEN** the combined equity line and each drawn benchmark line SHALL extend flat from that date to the current day at their last known value, rather than ending at the latest snapshot date

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
