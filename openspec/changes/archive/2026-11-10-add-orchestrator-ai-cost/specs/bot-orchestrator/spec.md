## ADDED Requirements

### Requirement: Orchestrator AI cost

The system SHALL report the AI (LLM) cost of each decision run and of each orchestrator,
sourced from the same LiteLLM spend log as the other AI cost figures. A run's cost SHALL be
the spend recorded under that run's own trace identifier; an orchestrator's cost SHALL be
the all-time sum of its runs' costs, including runs made before this reporting existed.
Costs for many runs or orchestrators SHALL be read with a single batched query rather than
one query per run.

Cost SHALL degrade like the existing AI cost figures: when the cost source is
unconfigured or cannot be read, costs SHALL be reported as absent (never a fabricated `0`
and never an error); when the source is reachable, a run or orchestrator with no recorded
spend SHALL report `0`.

#### Scenario: Orchestrator cost is the sum of its runs

- **WHEN** an orchestrator has two runs whose spend log entries total $0.12 and $0.08
- **THEN** the orchestrator's AI cost SHALL be $0.20 and each run SHALL report its own cost

#### Scenario: No recorded spend reads as zero

- **WHEN** the cost source is reachable and an orchestrator's runs have no spend entries
- **THEN** the orchestrator's AI cost SHALL be `0`

#### Scenario: Unavailable cost source degrades to absent

- **WHEN** the cost source is unconfigured or a query against it fails
- **THEN** orchestrator and run costs SHALL be reported as absent and the request SHALL
  still succeed

## MODIFIED Requirements

### Requirement: Decision run audit

Every run SHALL be persisted with its trigger (scheduled or manual), status, start and
finish times, duration, model, briefing, the AI's structured output, the applied actions
(stopped and deployed bot references), the rejected actions with reasons, the web
searches made, the AI call's **token usage** (requests, input tokens, output tokens and
total tokens) when the AI answered, and an error message when it failed. A run that ended
before the AI answered (skipped, or failed on a timeout or error) SHALL record no token
usage. The system SHALL let a client list an orchestrator's runs newest first, paginated,
and read a single run in full; run reads SHALL report the token usage and the run's AI cost.

#### Scenario: Run history lists newest first

- **WHEN** a client lists an orchestrator's runs
- **THEN** the system SHALL return them newest first with status, trigger, times and
  action counts

#### Scenario: Run detail shows decisions and rejections

- **WHEN** a client reads a partial run
- **THEN** the system SHALL return its market summary, applied actions, rejected actions
  with reasons, briefing and web searches

#### Scenario: Completed run records its token usage

- **WHEN** a run's AI call returns a decision
- **THEN** the run SHALL record the call's requests, input tokens, output tokens and total
  tokens, and run reads SHALL report them with the run's AI cost

#### Scenario: Run without an AI answer records no usage

- **WHEN** a run is skipped, or fails because the AI timed out
- **THEN** the run SHALL record no token usage

### Requirement: Orchestrator views

The orchestrator area SHALL offer:

- a **list view** of orchestrators (active and stopped by default, with an option to
  include archived), each with its label, status, cadence, value, return on its capital
  pool, active bots out of the maximum, all-time AI cost, and last run status and time;
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
