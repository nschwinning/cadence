## MODIFIED Requirements

### Requirement: Strategy bots navigation entry and views

The application shell SHALL provide a dedicated "Bots" navigation entry, distinct
from the paper-trading/portfolios entry, leading to a strategy-bots area with its
own create, list, and detail views. The create view SHALL be a dedicated bot build
form — separate from the AI portfolio build form — letting the user pick a strategy,
a **set of one or more equity assets from the universe**, an initial capital budget, a
benchmark, and the strategy's parameters (and optional take-profit / stop-loss). The
build form SHALL also let the user configure the **drawdown kill-switch threshold** — a
required, always-on control (not an enable/disable toggle) entered as a percentage,
defaulting to the configured default threshold so leaving it untouched preserves the
default behavior — and SHALL send it on creation so the user is not silently forced onto
the default. The asset selector SHALL be a **universe-backed, searchable picker** with
typeahead over eligible universe stocks that lets the user select multiple individual
assets and also offers a **"whole universe"** option; it SHALL NOT allow entering or
creating any asset that is not already in the universe. On successful creation the shell
SHALL navigate to the new bot's detail view. The list view SHALL show the user's bot
sessions with their key status and performance figures. The detail view SHALL show a
single bot session's KPI tiles, value chart, trade ledger, and its **current open
positions** (which may be several), reading from the strategy-bots endpoints. Bot
creation and tracking SHALL be reachable only through this area, not through the AI
paper-trading views.

#### Scenario: Bots navigation entry present and distinct

- **WHEN** the application shell renders its navigation
- **THEN** it SHALL show a "Bots" entry distinct from the paper-trading/portfolios
  entry, leading to the strategy-bots area

#### Scenario: Dedicated bot build form

- **WHEN** the user opens the bot create view
- **THEN** it SHALL present a bot-specific build form (strategy, a universe-backed
  searchable multi-select asset picker with a whole-universe option, initial capital
  budget, benchmark, parameters, optional take-profit/stop-loss, and the drawdown
  kill-switch threshold), not the AI portfolio build form

#### Scenario: Configuring the drawdown kill-switch

- **WHEN** the user opens the bot build form and enters a drawdown kill-switch percentage
  and creates the bot
- **THEN** the form SHALL default the drawdown kill-switch field to the configured default
  threshold, SHALL reject a percentage outside the valid range (greater than 0 and less
  than 100) with an inline invalid hint that blocks submission, and SHALL send the entered
  percentage as the session's drawdown threshold on creation

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
