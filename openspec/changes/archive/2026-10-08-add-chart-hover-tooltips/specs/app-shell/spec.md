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

When the chart is rendered, it SHALL display a **labelled x-axis** marking calendar
dates across the plotted history and a **labelled y-axis** marking portfolio value in
USD, so a user can read what any point on a line represents. Axis tick labels SHALL be
rendered legibly (not distorted by the chart's scaling). The chart SHALL also show a
**legend** identifying which line is the session's portfolio value and which line is
the benchmark; when the benchmark line is not drawn, the legend SHALL not imply a
benchmark line is present.

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
- **THEN** the view SHALL show dated x-axis labels and USD y-axis labels around the plot area

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

The paper-trading session list view SHALL display a **performance-comparison chart** that overlays every non-archived session (active, paused, stopped) on a shared time axis, so a user can compare sessions and see which performs best. The chart SHALL plot one line per session that has at least two value points, sharing a single y-scale across all plotted lines, and SHALL show a **legend** mapping each line's color to its session label. Sessions with fewer than two value points SHALL appear in the legend but SHALL NOT be plotted. The chart SHALL offer a **metric toggle** with two views, defaulting to the return view:

- **Return %** (default): each session's line SHALL be its cumulative total-return percentage, computed from the session's total value relative to its allocated capital, so sessions with different allocated capital and start dates are compared fairly and the highest line is the best performer.
- **Value ($)**: each session's line SHALL be its absolute total portfolio value in USD.

When the chart plots at least one line, it SHALL display a **labelled x-axis** marking calendar dates across the shared time axis and a **labelled y-axis** whose tick labels match the active metric — percentages in the Return % view and USD amounts in the Value $ view — and the y-axis labels SHALL update when the metric toggle switches. Axis tick labels SHALL be rendered legibly (not distorted by the chart's scaling).

When the chart plots at least one line, it SHALL support **hover inspection**: moving the pointer over the plot area SHALL identify the plotted point nearest the pointer across all plotted session lines and SHALL show a tooltip reporting that point's **session label**, its **date**, and its **value** formatted for the active metric — a percentage in the Return % view and a USD amount in the Value $ view. The tooltip SHALL be rendered legibly (not distorted by the chart's scaling) and SHALL be positioned near the hovered point without being clipped out of the chart area. The chart MAY also mark the hovered point visually. When the pointer leaves the plot area, the tooltip SHALL be dismissed. Hover inspection SHALL NOT change any plotted value and SHALL NOT appear when the insufficient-data placeholder, loading, or error state is shown.

When no non-archived session has enough value points to plot, the chart SHALL show an insufficient-data placeholder rather than an empty plot area. The chart SHALL show its own loading and error states while the comparison data is being fetched or if the fetch fails. The existing single-session value chart on the session detail view SHALL remain unchanged.

#### Scenario: Comparison chart overlays non-archived sessions

- **WHEN** a user opens the paper-trading session list and multiple non-archived sessions each have at least two value points
- **THEN** the chart SHALL render one line per such session on a shared y-scale with a legend identifying each session by its label

#### Scenario: Toggle between return % and absolute value

- **WHEN** a user switches the metric toggle from the default return view to the value view
- **THEN** the chart SHALL re-plot each session's line as its absolute portfolio value in USD, and switching back SHALL re-plot cumulative total-return percentage

#### Scenario: Return view is the default

- **WHEN** the comparison chart first renders
- **THEN** it SHALL show the cumulative total-return percentage view by default

#### Scenario: Axes are labelled and track the metric

- **WHEN** the comparison chart plots at least one line
- **THEN** the view SHALL show dated x-axis labels and y-axis labels formatted as percentages in the Return % view and as USD amounts in the Value $ view, and the y-axis labels SHALL change when the metric toggle is switched

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

The Dashboard SHALL present a combined equity curve as a single line equal to the summed value of the selected active sessions over the selected range, on a common date axis. A session SHALL contribute zero before its first recorded value (carry-forward thereafter). The Dashboard SHALL offer a selectable list of the active sessions, all selected by default, letting the user include or exclude each session; the selection SHALL also drive the hero tiles and the leaderboard. Toggling a session SHALL re-aggregate from already-fetched per-session data without issuing a new request per toggle. When no session is selected, the chart SHALL show an empty state instead of a line.

When the equity curve plots a line, it SHALL support **hover inspection**: moving the pointer over the plot area SHALL identify the plotted point nearest the pointer's horizontal position and SHALL show a tooltip reporting that point's **date** and the **summed equity value** in USD at that point. The tooltip SHALL be rendered legibly (not distorted by the chart's scaling) and SHALL be positioned near the hovered point without being clipped out of the chart area. The chart MAY also mark the hovered point visually. When the pointer leaves the plot area, the tooltip SHALL be dismissed. Hover inspection SHALL NOT change any plotted value and SHALL NOT appear when the empty state is shown.

#### Scenario: Summed line over selected sessions

- **WHEN** the Dashboard renders the equity curve with one or more sessions selected
- **THEN** it SHALL plot a single line equal to the sum of the selected sessions' values across the range, each session contributing zero before its first recorded value

#### Scenario: Toggling a session re-aggregates without refetch

- **WHEN** a user includes or excludes a session in the equity curve
- **THEN** the line, hero tiles, and leaderboard SHALL recompute from already-fetched data without a new request per toggle

#### Scenario: Hover reveals the summed value and date

- **WHEN** a user moves the pointer over the rendered combined equity curve
- **THEN** the view SHALL show a tooltip reporting the nearest point's date and the summed equity value in USD at that point

#### Scenario: Tooltip dismisses on leave

- **WHEN** the pointer leaves the equity curve's plot area
- **THEN** the view SHALL dismiss the hover tooltip

#### Scenario: No sessions selected

- **WHEN** no session is selected
- **THEN** the equity curve SHALL show an empty state rather than a line
