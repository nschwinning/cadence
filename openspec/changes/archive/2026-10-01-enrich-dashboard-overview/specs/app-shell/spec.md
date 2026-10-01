## ADDED Requirements

### Requirement: Dashboard global range selector

The Dashboard SHALL present a single range selector offering the choices `1D`, `1W`, `1M`, `YTD`, `1Y`, and `Max`, with one range active at a time. Changing the selected range SHALL drive every range-dependent section of the Dashboard (performance tiles, equity curve, portfolio leaderboard, automation failed-run count, recent activity, and universe performers) so that the whole view answers for the same horizon. The universe balance summary is range-independent and SHALL NOT change with the selector.

#### Scenario: Selecting a range updates the whole dashboard

- **WHEN** a user selects a different range
- **THEN** the performance tiles, equity curve, leaderboard, recent activity, and universe performers SHALL all refresh to that range while the universe balance summary stays unchanged

### Requirement: Dashboard aggregate performance tiles

The Dashboard SHALL present hero performance tiles aggregated over the active sessions currently selected in the equity curve: total current value, profit/loss over the selected range, money-weighted return over the selected range, and fees incurred within the range. The tiles SHALL reflect the current portfolio selection and the selected range.

#### Scenario: Tiles reflect range and selection

- **WHEN** a user changes the range or the set of selected portfolios
- **THEN** the hero tiles SHALL recompute to show aggregate value, range profit/loss, money-weighted range return, and range fees for the selected sessions

### Requirement: Dashboard combined equity curve

The Dashboard SHALL present a combined equity curve as a single line equal to the summed value of the selected active sessions over the selected range, on a common date axis. A session SHALL contribute zero before its first recorded value (carry-forward thereafter). The Dashboard SHALL offer a selectable list of the active sessions, all selected by default, letting the user include or exclude each session; the selection SHALL also drive the hero tiles and the leaderboard. Toggling a session SHALL re-aggregate from already-fetched per-session data without issuing a new request per toggle. When no session is selected, the chart SHALL show an empty state instead of a line.

#### Scenario: Summed line over selected sessions

- **WHEN** the Dashboard renders the equity curve with one or more sessions selected
- **THEN** it SHALL plot a single line equal to the sum of the selected sessions' values across the range, each session contributing zero before its first recorded value

#### Scenario: Toggling a session re-aggregates without refetch

- **WHEN** a user includes or excludes a session in the equity curve
- **THEN** the line, hero tiles, and leaderboard SHALL recompute from already-fetched data without a new request per toggle

#### Scenario: No sessions selected

- **WHEN** no session is selected
- **THEN** the equity curve SHALL show an empty state rather than a line

### Requirement: Dashboard portfolio leaderboard

The Dashboard SHALL present a leaderboard table of the selected active sessions, sorted by return over the selected range in descending order (best first). Each row SHALL show the portfolio's name, current value, range profit/loss, range return, and range fees, using the same money-weighted basis as the hero tiles, and SHALL link to that session's detail view. Return direction SHALL be visually distinguished (for example gains and losses colored differently). Deselecting a session in the equity curve SHALL remove it from the leaderboard.

#### Scenario: Sessions ranked by range return

- **WHEN** the Dashboard renders the leaderboard for a range
- **THEN** it SHALL list the selected sessions sorted by range return descending, each row showing name, value, range profit/loss, range return, and range fees, and linking to that session's detail view

#### Scenario: Selection narrows the leaderboard

- **WHEN** a user deselects a session
- **THEN** that session SHALL no longer appear in the leaderboard

### Requirement: Dashboard automation panel

The Dashboard SHALL present an automation panel showing the latest rebalance run's status and relative time with a link to that run, an indicator when a run is currently in flight, the count of failed runs within the selected range, and the approximate next scheduled run. The next run SHALL be labeled as approximate.

#### Scenario: Automation health shown

- **WHEN** the Dashboard renders the automation panel
- **THEN** it SHALL show the latest rebalance run (status, relative time, link), an in-flight indicator when applicable, the failed-run count within the range, and an approximate next-run time

### Requirement: Dashboard recent activity feed

The Dashboard SHALL present a recent-activity feed listing AI runs (build, rebalance, close) across sessions within the selected range, newest first and capped at a maximum count. Each entry SHALL show its kind, status, session label, relative time, and a link to that run.

#### Scenario: Recent activity listed

- **WHEN** the Dashboard renders the recent-activity feed for a range
- **THEN** it SHALL list the most recent AI runs within that range, newest first and capped, each showing kind, status, session label, relative time, and a link to the run

### Requirement: Dashboard universe section

The Dashboard SHALL present a universe section with a range-independent balance summary and range-dependent performers. The balance summary SHALL show the eligible versus ineligible split, the number of sectors represented, the largest sector's share, and the largest category's share. The performers SHALL show the best and worst tracked assets by market return over the selected range.

#### Scenario: Balance summary and performers shown

- **WHEN** the Dashboard renders the universe section
- **THEN** it SHALL show the current eligibility split, sectors represented, and largest sector and category shares, alongside the best and worst tracked assets by market return over the selected range

#### Scenario: Performers follow the range

- **WHEN** a user changes the selected range
- **THEN** the best/worst performers SHALL update to that range while the balance summary stays unchanged
