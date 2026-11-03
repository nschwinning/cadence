## MODIFIED Requirements

### Requirement: Strategy bots navigation entry and views

The application shell SHALL provide a dedicated "Bots" navigation entry, distinct
from the paper-trading/portfolios entry, leading to a strategy-bots area with its
own create, list, and detail views. The create view SHALL be a dedicated bot build
form — separate from the AI portfolio build form — letting the user pick a strategy,
a **set of one or more equity assets from the universe**, an initial capital budget, a
benchmark, and the strategy's parameters (and optional take-profit / stop-loss). The
asset selector SHALL be a **universe-backed, searchable picker** with typeahead over
eligible universe stocks that lets the user select multiple individual assets and also
offers a **"whole universe"** option; it SHALL NOT allow entering or creating any asset
that is not already in the universe. On successful creation the shell SHALL navigate to
the new bot's detail view. The list view SHALL show the user's bot sessions with their
key status and performance figures. The detail view SHALL show a single bot session's
KPI tiles, value chart, trade ledger, and its **current open positions** (which may be
several), reading from the strategy-bots endpoints. Bot creation and tracking SHALL be
reachable only through this area, not through the AI paper-trading views.

#### Scenario: Bots navigation entry present and distinct

- **WHEN** the application shell renders its navigation
- **THEN** it SHALL show a "Bots" entry distinct from the paper-trading/portfolios
  entry, leading to the strategy-bots area

#### Scenario: Dedicated bot build form

- **WHEN** the user opens the bot create view
- **THEN** it SHALL present a bot-specific build form (strategy, a universe-backed
  searchable multi-select asset picker with a whole-universe option, initial capital
  budget, benchmark, parameters, optional take-profit/stop-loss), not the AI portfolio
  build form

#### Scenario: Picker admits only existing universe assets

- **WHEN** the user searches for and selects assets in the bot build form
- **THEN** the picker SHALL offer only eligible universe stocks and SHALL NOT allow
  submitting a symbol that is not already in the universe

#### Scenario: Creating a bot navigates to its detail view

- **WHEN** the user successfully creates a bot
- **THEN** the shell SHALL navigate to that bot's detail view

#### Scenario: Bot list and detail

- **WHEN** the user opens the Bots area and selects a bot
- **THEN** the list view SHALL show the user's bot sessions and the detail view SHALL
  show that bot's KPI tiles, value chart, trade ledger, and current open positions from
  the strategy-bots endpoints

## ADDED Requirements

### Requirement: Strategy explanation navigation entry and page

The application shell SHALL offer, within the Bots area, a navigation affordance to a
dedicated **strategy explanation page**, and SHALL mark it active when shown, consistent
with the shell's other navigation entries. The page SHALL explain what the available
strategy (MA Crossover) does, using the strategy explanation obtained from the
strategy-bots catalog, accompanied by an **illustrative chart** that depicts a fast and a
slow moving average with entry and exit markers at their crossovers. The page SHALL also
document the optional risk controls and capital management the bots apply — ATR
risk-based position sizing, the maximum per-name cap, the maximum number of concurrent
positions, the shared capital budget ceiling, take-profit, stop-loss, and the drawdown
kill-switch — in readable grouped sections. While the strategy catalog is loading the
page SHALL show a loading state, and if the request fails it SHALL show an error state
rather than a blank or broken page.

#### Scenario: Navigate to the strategy explanation page

- **WHEN** a user selects the strategy explanation affordance in the Bots area
- **THEN** the application SHALL render the strategy explanation page within the shell and
  mark the entry active without a full page reload

#### Scenario: Strategy mechanic explained with an illustrative chart

- **WHEN** the strategy explanation page loads the strategy catalog successfully
- **THEN** it SHALL display the strategy's explanation text and an illustrative chart
  showing fast and slow moving averages with entry/exit markers at their crossovers

#### Scenario: Risk controls and capital management documented

- **WHEN** the strategy explanation page is shown
- **THEN** it SHALL document ATR risk-based sizing, the per-name cap, the maximum
  concurrent positions, the shared budget ceiling, take-profit, stop-loss, and the
  drawdown kill-switch in readable grouped sections

#### Scenario: Loading and error states

- **WHEN** the strategy catalog is loading or the request fails
- **THEN** the page SHALL show a loading state while pending and an error state on failure
  instead of the content
