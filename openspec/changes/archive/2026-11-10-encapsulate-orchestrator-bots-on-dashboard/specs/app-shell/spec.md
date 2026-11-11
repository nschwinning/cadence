## ADDED Requirements

### Requirement: Orchestrator bots on the Bots list

The Bots list SHALL keep listing every bot session, including bots deployed by a bot
orchestrator, so each can still be opened. A bot deployed by an orchestrator SHALL be visibly
marked as such in the list, naming its orchestrator and linking to the orchestrator's detail
view. Every bot in the list and on its detail view SHALL be shown under its display name.

#### Scenario: Orchestrator bot is badged and linked

- **WHEN** the Bots list shows a bot deployed by the orchestrator "First Orchestrator"
- **THEN** its row SHALL carry a marker naming "First Orchestrator" that links to that
  orchestrator's detail view

#### Scenario: Manual bots carry no orchestrator marker

- **WHEN** the Bots list shows a manually created bot
- **THEN** its row SHALL carry no orchestrator marker

## MODIFIED Requirements

### Requirement: Dashboard combined equity curve

The Dashboard SHALL present a combined equity curve as a single line equal to the summed value of the selected active sessions over the selected range, on a common date axis. The selectable sessions SHALL include AI paper-trading sessions, manually created strategy-bot sessions and bot orchestrators, each visually badged by its kind (AI, bot or orchestrator) in the selection list; an orchestrator is one selectable series covering its bots. A session SHALL contribute zero before its first recorded value (carry-forward thereafter). The common date axis SHALL span the union of the selected sessions' snapshot dates extended to a trailing horizon of the current day (US Eastern), so the combined line — and the benchmark lines described below — extend flat across trailing non-trading days (for example the current weekend) at their last known value rather than ending at the latest snapshot date. The Dashboard SHALL offer a selectable list of the active sessions, all selected by default, letting the user include or exclude each session; the selection SHALL also drive the hero tiles and the leaderboard. Toggling a session SHALL re-aggregate from already-fetched per-session data without issuing a new request per toggle. When no session is selected, the chart SHALL show an empty state instead of a line.

The chart SHALL also overlay **benchmark index lines** on the same dollar axis. It SHALL present a benchmark legend listing every index in the benchmark catalog, each individually selectable, with the S&P 500 selected by default and the others deselected. For each selected benchmark that has price data over the range, the chart SHALL draw a line equal to the **sum over the selected sessions of a buy-and-hold of each session's contributed capital in that index** — for each selected session, its opening capital is treated as invested in the index on the session's first date and each later capital increase as invested on its effective date, each held thereafter and valued forward by the index's price movement, and these per-session positions are summed on the common date axis. Consequently the benchmark line starts from zero before any selected session has opened and **steps up as each selected session opens** (and on each later capital increase), mirroring how the combined equity line aggregates, so the two curves are directly comparable in USD (no percent/dollar toggle). A selected benchmark that has no price data over the range SHALL draw no line, and its legend control SHALL be inert rather than erroring. Benchmark lines SHALL be visually distinguishable from the portfolio line and from one another. Toggling a benchmark SHALL add or remove its line without issuing a new request, and changing the session selection SHALL re-aggregate the benchmark lines over the newly selected sessions. When no session is selected, no benchmark lines SHALL be drawn (the empty state is shown instead).

When the equity curve plots a line, it SHALL support **hover inspection**: moving the pointer over the plot area SHALL identify the plotted point nearest the pointer's horizontal position and SHALL show a tooltip reporting that point's **date**, the **summed equity value** in USD at that point, and the aggregated USD value of each currently-drawn benchmark line at that point. The tooltip SHALL be rendered legibly (not distorted by the chart's scaling) and SHALL be positioned near the hovered point without being clipped out of the chart area. The chart MAY also mark the hovered point visually. When the pointer leaves the plot area, the tooltip SHALL be dismissed. Hover inspection SHALL NOT change any plotted value and SHALL NOT appear when the empty state is shown.

#### Scenario: Summed line over selected sessions

- **WHEN** the Dashboard renders the equity curve with one or more sessions selected
- **THEN** it SHALL plot a single line equal to the sum of the selected sessions' values across the range, each session contributing zero before its first recorded value

#### Scenario: Selection list badges AI and bot sessions

- **WHEN** the Dashboard renders the session selection list and both AI sessions and strategy-bot sessions are active
- **THEN** each selectable session SHALL be badged by its kind (AI or bot), and selecting a bot session SHALL include it in the summed equity line like any other session

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

#### Scenario: Orchestrator is one selectable series

- **WHEN** the dashboard renders with an active orchestrator that has deployed bots
- **THEN** the selection list SHALL show one entry badged as an orchestrator and no
  separate entries for its bots, and selecting it SHALL add the orchestrator's value to
  the summed equity line

### Requirement: Dashboard portfolio leaderboard

The Dashboard SHALL present a leaderboard table of the selected active sessions, sorted by return over the selected range in descending order (best first). The leaderboard SHALL include AI paper-trading sessions, manually created strategy-bot sessions and bot orchestrators, each row visually badged by its kind (AI, bot or orchestrator); bots deployed by an orchestrator SHALL NOT appear as rows of their own. Each row SHALL show the portfolio's name, current value, range realised profit/loss, range unrealised profit/loss, range return, and range fees, using the same money-weighted basis as the hero tiles, and SHALL link to that session's detail view (an AI row links to the paper-trading session detail; a bot row links to the bot session detail; an orchestrator row links to the orchestrator detail). The current value column SHALL be marked as a point-in-time/live figure, and the range-scoped columns (realised profit/loss, unrealised profit/loss, return, and fees) SHALL be visually grouped under an indication of the active range, so the user can tell the point-in-time value apart from the range-scoped figures. Return direction and the realised and unrealised profit/loss SHALL be visually distinguished by sign (for example gains and losses colored differently). Deselecting a session in the equity curve SHALL remove it from the leaderboard.

#### Scenario: Sessions ranked by range return

- **WHEN** the Dashboard renders the leaderboard for a range
- **THEN** it SHALL list the selected sessions sorted by range return descending, each row showing name, value, range realised profit/loss, range unrealised profit/loss, range return, and range fees, and linking to that session's detail view

#### Scenario: Leaderboard includes and badges bot rows

- **WHEN** the Dashboard renders the leaderboard and a strategy-bot session is selected
- **THEN** the bot session SHALL appear as a leaderboard row badged as a bot, ranked by its range return alongside AI sessions, linking to the bot session's detail view

#### Scenario: Leaderboard distinguishes point-in-time value from range columns

- **WHEN** the Dashboard renders the leaderboard
- **THEN** the current value column SHALL be marked as a point-in-time/live figure and the realised, unrealised, return, and fees columns SHALL be grouped under an indication of the active range

#### Scenario: Selection narrows the leaderboard

- **WHEN** a user deselects a session
- **THEN** that session SHALL no longer appear in the leaderboard

#### Scenario: Leaderboard shows the orchestrator, not its bots

- **WHEN** the leaderboard renders with an active orchestrator that has deployed bots
- **THEN** it SHALL show one row badged as an orchestrator, ranked by its range return and
  linking to the orchestrator's detail view, and SHALL NOT show its bots as separate rows
