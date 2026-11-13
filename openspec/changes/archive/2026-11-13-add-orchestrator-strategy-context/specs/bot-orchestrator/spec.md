## MODIFIED Requirements

### Requirement: Decision briefing

Before invoking the AI, a run SHALL assemble a **briefing** from stored data, without
adding new data providers. The briefing SHALL contain:

- **Market technicals** — for each configured benchmark index with stored daily closes,
  the technical indicator snapshot computed from those closes (trend regime relative to
  the 50- and 200-day averages, momentum, RSI, rate of change, drawdown from its high).
- **Sector breadth** — for each sector of the eligible universe equities: the number of
  equities, the share passing the trend gate, the share in an up-trend regime, and the
  average RSI and distance from the 52-week high, from the latest per-asset indicator
  snapshots.
- **Sector news tone** — for each sector, the aggregate of its equities' news-sentiment
  signals (average score and counts of positive, neutral and negative tickers), or an
  indication that news sentiment is unavailable.
- **Candidate tickers** — the eligible universe equities with sector, trend-gate result,
  key indicators and news tone, from which the AI may choose bot tickers.
- **Presets** — every preset in the bot preset catalog with its key, display name,
  description, course reference, strategy key, strategy style, strategy parameters and risk
  controls.
- **Strategies** — once for each strategy used by a listed preset: its key, display name,
  style (trend, momentum, breakout, mean-reversion or regime-switching) and plain-language
  explanation of how it trades.
- **Running bots** — each of the orchestrator's active bots with its preset, tickers, days
  active, allocated capital, current value, return, maximum drawdown and trade statistics,
  plus bots stopped but still being sold.
- **Limits** — free capital, open bot slots, the per-bot capital minimum ($1,000) and
  maximum, and the per-bot ticker limit.

Missing inputs (no indicator snapshot, no benchmark closes, no sentiment) SHALL be marked
unavailable rather than failing the run. The briefing SHALL be stored with the run.

#### Scenario: Briefing aggregates sectors from per-asset data

- **WHEN** a run builds its briefing with three eligible technology equities, two of which
  pass the trend gate
- **THEN** the technology entry SHALL report three equities and a two-thirds gate pass share

#### Scenario: Unavailable sentiment does not fail the run

- **WHEN** news sentiment is not configured
- **THEN** the briefing SHALL mark sector news tone as unavailable and the run SHALL
  continue

#### Scenario: Briefing lists running bots with performance

- **WHEN** an orchestrator has two active bots
- **THEN** the briefing SHALL list both with their preset, tickers, days active, allocated
  capital, current value and return

#### Scenario: Briefing explains each strategy once

- **WHEN** a run builds its briefing and several presets share one strategy
- **THEN** the briefing SHALL list that strategy once with its style and explanation, and each
  of those presets SHALL carry the strategy's key and style

#### Scenario: Every strategy has a style

- **WHEN** a strategy is registered
- **THEN** it SHALL have one of the styles trend, momentum, breakout, mean-reversion or
  regime-switching

### Requirement: Orchestrator views

The orchestrator area SHALL offer:

- a **list view** of orchestrators (active and stopped by default, with an option to
  include archived), each with its label, status, cadence, value, return on its capital
  pool, active bots out of the maximum, all-time AI cost, and last run status and time;
- on the list view, a read-only **preset catalog** listing every preset an orchestrator may
  deploy, each with its display name, description and key, its strategy (linking to that
  strategy's guide page) and course reference, its strategy parameters, and its take-profit,
  stop-loss (each shown as "Off" when disabled) and drawdown limit;
- a **deploy form** (opened from the list view) with the label, capital pool, maximum
  parallel bots, maximum share per bot, maximum tickers per bot, cadence, AI model and
  benchmark, pre-filled with the defaults and validated like the backend; on success it
  SHALL navigate to the new orchestrator's detail view;
- a **detail view** showing the configuration; capital tiles for value, return, free
  capital and allocated capital, and an **AI cost** tile with the orchestrator's all-time
  AI cost; its bots (active, being sold, and finished), each linking to the bot's detail
  view with preset, tickers, allocated capital, current value and status; and its run
  history with each run's status, trigger, time, token usage, AI cost, market summary,
  applied and rejected actions with reasons. The detail view SHALL offer **Run now**,
  **Stop** (with confirmation) and **Archive** actions appropriate to the status, and SHALL
  refresh while a run is queued or running.

AI costs that are absent SHALL render as an em dash ("—"), never as `$0.00`; a readable
cost of zero SHALL render as `$0.00`.

#### Scenario: List shows orchestrators with key figures

- **WHEN** a user opens the orchestrator list
- **THEN** each orchestrator SHALL show its label, status, cadence, value, return, active
  bots out of the maximum, AI cost, and last run status

#### Scenario: Deploy form opens with defaults

- **WHEN** a user opens the deploy form
- **THEN** it SHALL be pre-filled with 3 parallel bots, a 50% per-bot share, 5 tickers per
  bot and a daily cadence, and SHALL block submission for capital below $5,000

#### Scenario: Detail view shows bots and runs

- **WHEN** a user opens an orchestrator's detail view
- **THEN** it SHALL show the capital tiles, its bots linking to their detail views, and its
  run history with market summaries and actions

#### Scenario: Run now from the detail view

- **WHEN** a user selects Run now on an active orchestrator with no run in progress
- **THEN** a run SHALL be queued and the view SHALL refresh until it finishes

#### Scenario: Stop requires confirmation

- **WHEN** a user selects Stop on an active orchestrator
- **THEN** the view SHALL ask for confirmation before stopping it and its bots

#### Scenario: Detail view shows AI cost and per-run usage

- **WHEN** a user opens the detail view of an orchestrator whose runs have recorded usage
  and cost
- **THEN** the view SHALL show an AI cost tile with the all-time cost, and each run in the
  history SHALL show its total tokens and its cost

#### Scenario: Unavailable cost renders as an em dash

- **WHEN** the cost source is unavailable
- **THEN** the AI cost tile and the per-run costs SHALL render as "—", not `$0.00`

#### Scenario: List view shows the preset catalog

- **WHEN** a user opens the orchestrator list
- **THEN** it SHALL list every catalog preset with its strategy linking to the strategy's guide
  page, its parameters, and its risk controls, showing a disabled take-profit or stop-loss as
  "Off"
