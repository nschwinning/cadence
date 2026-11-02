## ADDED Requirements

### Requirement: Strategy bots navigation entry and views

The application shell SHALL provide a dedicated "Bots" navigation entry, distinct
from the paper-trading/portfolios entry, leading to a strategy-bots area with its
own create, list, and detail views. The create view SHALL be a dedicated bot build
form — separate from the AI portfolio build form — letting the user pick a strategy,
an asset from the universe, an initial capital, a benchmark, and the strategy's
parameters (and optional take-profit / stop-loss). The list view SHALL show the
user's bot sessions with their key status and performance figures. The detail view
SHALL show a single bot session's KPI tiles, value chart, and trade ledger, reading
from the strategy-bots endpoints. Bot creation and tracking SHALL be reachable only
through this area, not through the AI paper-trading views.

#### Scenario: Bots navigation entry present and distinct

- **WHEN** the application shell renders its navigation
- **THEN** it SHALL show a "Bots" entry distinct from the paper-trading/portfolios
  entry, leading to the strategy-bots area

#### Scenario: Dedicated bot build form

- **WHEN** the user opens the bot create view
- **THEN** it SHALL present a bot-specific build form (strategy, universe asset,
  initial capital, benchmark, parameters, optional take-profit/stop-loss), not the
  AI portfolio build form

#### Scenario: Bot list and detail

- **WHEN** the user opens the Bots area and selects a bot
- **THEN** the list view SHALL show the user's bot sessions and the detail view SHALL
  show that bot's KPI tiles, value chart, and trade ledger from the strategy-bots
  endpoints

## MODIFIED Requirements

### Requirement: Dashboard combined equity curve

The Dashboard SHALL present a combined equity curve as a single line equal to the summed value of the selected active sessions over the selected range, on a common date axis. The selectable sessions SHALL include both AI paper-trading sessions and strategy-bot sessions, each visually badged by its kind (AI or bot) in the selection list. A session SHALL contribute zero before its first recorded value (carry-forward thereafter). The Dashboard SHALL offer a selectable list of the active sessions, all selected by default, letting the user include or exclude each session; the selection SHALL also drive the hero tiles and the leaderboard. Toggling a session SHALL re-aggregate from already-fetched per-session data without issuing a new request per toggle. When no session is selected, the chart SHALL show an empty state instead of a line.

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

### Requirement: Dashboard portfolio leaderboard

The Dashboard SHALL present a leaderboard table of the selected active sessions, sorted by return over the selected range in descending order (best first). The leaderboard SHALL include both AI paper-trading sessions and strategy-bot sessions, each row visually badged by its kind (AI or bot). Each row SHALL show the portfolio's name, current value, range realised profit/loss, range unrealised profit/loss, range return, and range fees, using the same money-weighted basis as the hero tiles, and SHALL link to that session's detail view (an AI row links to the paper-trading session detail; a bot row links to the bot session detail). The current value column SHALL be marked as a point-in-time/live figure, and the range-scoped columns (realised profit/loss, unrealised profit/loss, return, and fees) SHALL be visually grouped under an indication of the active range, so the user can tell the point-in-time value apart from the range-scoped figures. Return direction and the realised and unrealised profit/loss SHALL be visually distinguished by sign (for example gains and losses colored differently). Deselecting a session in the equity curve SHALL remove it from the leaderboard.

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
