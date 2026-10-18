## ADDED Requirements

### Requirement: Stable paper-trading session ordering and per-portfolio chart color

Paper-trading sessions SHALL be presented in one stable, predictable order everywhere they are listed or plotted, and each session SHALL keep one stable color in the comparison chart, so a returning user can recognise a given portfolio by its position and its color rather than seeing them reshuffle between visits.

The paper-trading **session list** SHALL order sessions by their creation date, oldest first. This order SHALL NOT depend on when a session was last updated, rebalanced, or otherwise touched, so adding a new session appends it at the end rather than reordering the existing ones.

The **comparison chart's lines and its legend** SHALL be ordered by session creation date, oldest first, consistent with the session list.

Each session's **line color** in the comparison chart SHALL be derived from the session's own stable identity, not from its position in the current render. The same session SHALL therefore be drawn in the same color across page visits and regardless of which other sessions are currently plotted or which sessions are archived.

#### Scenario: Session list is ordered oldest-created first

- **WHEN** a user views the paper-trading session list with multiple sessions
- **THEN** the sessions SHALL be ordered by creation date, oldest first, independent of when each was last updated

#### Scenario: A new session appends without reordering

- **WHEN** a new session is created and the user reloads the session list
- **THEN** the new session SHALL appear at the end of the list and the existing sessions SHALL keep their previous relative order

#### Scenario: Comparison chart order matches the list

- **WHEN** the comparison chart renders lines for several sessions
- **THEN** the chart's lines and its legend SHALL be ordered by session creation date, oldest first, consistent with the session list

#### Scenario: A portfolio keeps its color across visits

- **WHEN** a user views the comparison chart, leaves, and returns — or when the set of plotted sessions changes (for example a session is archived)
- **THEN** each session that is still plotted SHALL be drawn in the same color as before, because its color is keyed to the session's stable identity rather than its render position

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

When the chart plots at least one line, it SHALL display a **labelled x-axis** marking several calendar dates spread across the shared time axis — more than just the first and last points — and a **labelled y-axis** whose tick labels match the active metric — percentages in the Return % view and USD amounts in the Value $ view — and the y-axis labels SHALL update when the metric toggle switches. Axis tick labels SHALL be rendered legibly (not distorted by the chart's scaling).

When the chart plots at least one line, it SHALL support **hover inspection**: moving the pointer over the plot area SHALL identify the plotted point nearest the pointer across all plotted session lines and SHALL show a tooltip reporting that point's **session label**, its **date**, and its **value** formatted for the active metric — a percentage in the Return % view and a USD amount in the Value $ view. The tooltip SHALL be rendered legibly (not distorted by the chart's scaling) and SHALL be positioned near the hovered point without being clipped out of the chart area. The chart MAY also mark the hovered point visually. When the pointer leaves the plot area, the tooltip SHALL be dismissed. Hover inspection SHALL NOT change any plotted value and SHALL NOT appear when the insufficient-data placeholder, loading, or error state is shown.

When no non-archived session has enough value points to plot, the chart SHALL show an insufficient-data placeholder rather than an empty plot area. The chart SHALL show its own loading and error states while the comparison data is being fetched or if the fetch fails. The existing single-session value chart on the session detail view SHALL remain unchanged.

#### Scenario: Comparison chart overlays non-archived sessions

- **WHEN** a user opens the paper-trading session list and multiple non-archived sessions each have at least two value points
- **THEN** the chart SHALL render one line per such session on a shared y-scale with a legend identifying each session by its label

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
