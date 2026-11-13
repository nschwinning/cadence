# bot-orchestrator Specification

## Purpose

An AI bot orchestrator that manages a portfolio of strategy bots within user-set limits:
on a daily, weekly or monthly cadence it reads a market and sector briefing and decides
which course-preset bots to deploy and which running bots to stop, with every decision
validated against its capital pool and limits and recorded for review.

## Requirements

### Requirement: Orchestrator configuration and lifecycle

The system SHALL let a client deploy a bot orchestrator with a label, a **capital pool**
of at least $5,000, a **maximum number of parallel bots** between 1 and 10 (default 3), a
**maximum share of the pool per bot** greater than 0 and at most 100% (default 50%), a
**maximum number of tickers per bot** between 1 and 10 (default 5), a **decision
cadence** of daily, weekly or monthly, an **AI model** from the supported model list, and
a **benchmark** from the benchmark catalog. Invalid configuration SHALL be rejected.
Deploying an orchestrator SHALL NOT invoke any AI model and SHALL NOT create any bot.

An orchestrator SHALL have a status of active, stopped or archived. The system SHALL let a
client stop an active orchestrator and archive a stopped one. Stopping an orchestrator
SHALL stop every active bot it deployed, with stop reason orchestrator (so their
positions are sold), and SHALL end its decision runs. Only a stopped orchestrator SHALL
be archivable, and archived orchestrators SHALL be hidden from the default listing.

#### Scenario: Deploy an orchestrator

- **WHEN** a client deploys an orchestrator with a valid label, capital, limits, cadence,
  model and benchmark
- **THEN** the system SHALL persist an active orchestrator whose free capital equals its
  capital pool, with no bots and no runs, without invoking any AI model

#### Scenario: Reject invalid configuration

- **WHEN** a client deploys an orchestrator with capital below $5,000, a parallel-bot limit
  outside 1–10, a per-bot share outside (0, 100%], a ticker limit outside 1–10, an unknown
  cadence, model or benchmark
- **THEN** the system SHALL reject the request and create nothing

#### Scenario: Stopping an orchestrator stops its bots

- **WHEN** a client stops an active orchestrator that has active bots
- **THEN** each of those bots SHALL be stopped with stop reason orchestrator, the
  orchestrator SHALL become stopped, and no further decision runs SHALL be started for it

#### Scenario: Archive only a stopped orchestrator

- **WHEN** a client archives an orchestrator that is still active
- **THEN** the system SHALL reject the request

### Requirement: Orchestrator capital pool

Each orchestrator SHALL track its **free capital**. Deploying a bot SHALL move the bot's
allocated capital from free capital into the bot, which uses it as its initial capital.
When a bot deployed by the orchestrator is no longer active and holds no open positions,
the system SHALL return the bot's remaining cash to the orchestrator's free capital
exactly once and record that it was returned. Gains and losses therefore flow back into
the pool. Free capital SHALL never go negative, and a deploy SHALL never allocate more
than the free capital available at that moment.

The orchestrator's **value** SHALL be its free capital plus the current value of each of
its bots whose capital has not yet been returned; its **allocated capital** SHALL be the
sum of the initial capital of those bots. Reads SHALL report the capital pool, free
capital, allocated capital, value, and the counts of active bots and of stopped bots still
being sold.

#### Scenario: Deploy moves capital out of the pool

- **WHEN** a decision deploys a bot with $3,000 from an orchestrator with $10,000 free
- **THEN** the bot SHALL start with $3,000 of capital and the orchestrator's free capital
  SHALL become $7,000

#### Scenario: A flat stopped bot returns its cash

- **WHEN** a bot deployed by the orchestrator is stopped and its positions have all been
  sold, leaving $3,240 of cash
- **THEN** $3,240 SHALL be added to the orchestrator's free capital once, and the bot
  SHALL be recorded as returned

#### Scenario: Capital is not returned twice

- **WHEN** a bot's capital has already been returned and the return check runs again
- **THEN** the orchestrator's free capital SHALL NOT change

#### Scenario: Value includes unreturned bots

- **WHEN** a client reads an orchestrator with $4,000 free and two unreturned bots worth
  $3,100 and $2,950
- **THEN** the orchestrator's value SHALL be $10,050

### Requirement: Scheduled decision runs

The system SHALL provide a cron-triggered endpoint, protected by the same cron token as
the other scheduled jobs, that starts a **decision run** for every active orchestrator that
is **due** for its cadence. Due-ness SHALL follow the AI-portfolio rebalancing rules in the
America/New_York calendar: daily orchestrators are due every trigger; weekly orchestrators
are due when no counting run has happened in the current ISO week; monthly orchestrators
are due when no counting run has happened in the current calendar month; an orchestrator
with no counting run is due. Only succeeded and partial runs SHALL count; failed and
skipped runs SHALL leave the orchestrator due so it is retried on the next trigger. The
trigger SHALL be scheduled on weekdays **before the market opens** (09:00
America/New_York) so decisions are in place for the opening bell. An orchestrator
SHALL have at most one run queued or running at a time.

A run SHALL be **skipped** without invoking the AI when the current day is not a trading
day (a weekend or market holiday, as reported by the broker's market calendar). A run SHALL
NOT place orders itself: the bots it stops are sold, and the bots it deploys start
trading, at the first intraday tick while the market is open. Runs SHALL be
executed in the background so the endpoint returns promptly, reporting how many runs were
started and how many orchestrators were skipped as not due or already running.

#### Scenario: Weekly orchestrator runs once per week

- **WHEN** the trigger fires on a Tuesday for a weekly orchestrator whose last counting run
  was on the Monday of the same ISO week
- **THEN** the system SHALL NOT start a run for it

#### Scenario: Failed run is retried on the next trigger

- **WHEN** an orchestrator's only run this period failed and the trigger fires again
- **THEN** the orchestrator SHALL be due and a new run SHALL be started

#### Scenario: Non-trading day skips the run

- **WHEN** a decision run starts on a weekend or market holiday
- **THEN** the run SHALL be recorded as skipped without invoking the AI, and the
  orchestrator SHALL remain due

#### Scenario: Pre-open run takes effect at the open

- **WHEN** a decision run completes before the market opens on a trading day, stopping one
  bot and deploying another
- **THEN** the stopped bot's positions SHALL be sold, and the deployed bot SHALL begin
  evaluating entries, at the first intraday tick after the market opens

#### Scenario: Unauthenticated trigger rejected

- **WHEN** the trigger endpoint is called without a valid cron token
- **THEN** the system SHALL reject the call and start no runs

#### Scenario: No overlapping runs

- **WHEN** the trigger fires while an orchestrator already has a run queued or running
- **THEN** the system SHALL NOT start a second run for it

### Requirement: Manual decision run

The system SHALL let a client start a decision run for an active orchestrator on demand,
regardless of its cadence. A manual run SHALL follow the same trading-day rule, validation
and audit as a scheduled run and SHALL count toward the cadence when it succeeds. A manual
run SHALL be rejected for an orchestrator that is not active or that already has a run
queued or running.

#### Scenario: Run now

- **WHEN** a client starts a run for an active orchestrator with no run in progress
- **THEN** the system SHALL queue a decision run and return it

#### Scenario: Run now rejected while a run is in progress

- **WHEN** a client starts a run for an orchestrator that already has a run queued or running
- **THEN** the system SHALL reject the request

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

### Requirement: AI decision and its application

A run SHALL invoke the orchestrator's AI model with the briefing. The AI MAY use web search
for market and sector news within a fixed per-run search budget, and SHALL return a
structured decision: a short **market summary**, a list of **bots to stop** (each an active
bot of this orchestrator with a reason), and a list of **bots to deploy** (each a preset
key, a set of tickers, a capital amount and a rationale). The AI MAY decide to change
nothing.

The system SHALL validate and apply the decision deterministically: first every stop, then
every deploy in the order given. A stop SHALL be rejected if the bot is not an active bot
of this orchestrator. A deploy SHALL be rejected if the preset is unknown; if any ticker is
not an eligible universe equity; if it has no tickers, duplicate tickers or more tickers
than the per-bot limit; if its capital is below $1,000, above the per-bot maximum share of
the pool's value, or above the free capital remaining; or if no bot slot remains (active
bots count against the limit, and slots freed by this run's stops are available). An
accepted deploy SHALL create a bot from the preset with the chosen tickers, capital and the
orchestrator's benchmark, with origin orchestrator. Rejected actions SHALL be recorded with
their reason and SHALL NOT stop the other actions.

A run SHALL be **succeeded** when every action was applied (including deciding to change
nothing), **partial** when at least one action was applied and at least one was rejected,
and **failed** when the AI errors, times out or returns no valid output, or when every
action was rejected. A failed run SHALL apply nothing.

#### Scenario: Stops are applied before deploys

- **WHEN** an orchestrator at its parallel-bot limit decides to stop one bot and deploy one
  new bot
- **THEN** the stop SHALL be applied first and the deploy SHALL use the freed slot

#### Scenario: Over-budget deploy is rejected

- **WHEN** a decision deploys a bot with more capital than the free capital remaining
- **THEN** that deploy SHALL be rejected with a reason and other valid actions SHALL still
  be applied, making the run partial

#### Scenario: Unknown preset or ineligible ticker is rejected

- **WHEN** a decision deploys an unknown preset or a ticker that is not an eligible
  universe equity
- **THEN** that deploy SHALL be rejected with a reason and no bot SHALL be created for it

#### Scenario: Accepted deploy creates a preset bot

- **WHEN** a decision deploys the Turtle Breakout preset on two eligible tickers with $2,500
- **THEN** a bot SHALL be created from that preset trading those tickers with $2,500 of
  capital, the orchestrator's benchmark, and origin orchestrator

#### Scenario: AI timeout fails the run without changes

- **WHEN** the AI does not answer within the timeout
- **THEN** the run SHALL be failed, no bot SHALL be stopped or deployed, and the
  orchestrator SHALL remain due

#### Scenario: Deciding to change nothing succeeds

- **WHEN** the AI returns a market summary with no stops and no deploys
- **THEN** the run SHALL be succeeded and count toward the cadence

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

### Requirement: Orchestrator daily snapshots

The evening bot snapshot job SHALL, after recording the bots' daily snapshots, record one
daily snapshot per **active** orchestrator for that date, capturing its value, free
capital, allocated capital and number of active bots (as defined by the capital-pool
requirement). There SHALL be at most one snapshot per orchestrator per date; running the
job again on the same date SHALL update that date's snapshot rather than add another.
Stopped and archived orchestrators SHALL NOT be snapshotted. Before snapshotting, the job
SHALL settle any capital that finished bots return to the pool, so the figures are
current.

#### Scenario: Active orchestrator is snapshotted daily

- **WHEN** the evening snapshot job runs with one active orchestrator
- **THEN** the system SHALL record a snapshot for that date with its value, free capital,
  allocated capital and active bots

#### Scenario: Rerun on the same day updates the snapshot

- **WHEN** the job runs twice on the same date
- **THEN** the orchestrator SHALL have a single snapshot for that date carrying the latest
  figures

#### Scenario: Stopped orchestrators are not snapshotted

- **WHEN** the job runs while an orchestrator is stopped or archived
- **THEN** no snapshot SHALL be recorded for it

### Requirement: Orchestrator notifications

Scheduled runs SHALL send a push notification when notifications are configured: on
success or partial success, a summary naming the orchestrator and the bots stopped and
deployed; on failure, the orchestrator and the error. Skipped runs and manual runs SHALL NOT
notify. A notification failure SHALL NOT fail the run.

In addition, the evening snapshot job SHALL send **one daily P&L notification per active
orchestrator** after recording its snapshot, titled with the orchestrator's label, carrying:

- its value and **day change** as an amount and a percentage, against the previous
  snapshot's value or, when there is no earlier snapshot, against the capital pool (the
  percentage is omitted when that baseline is not positive);
- its **total return** on the capital pool as an amount and a percentage;
- its free capital, allocated capital, and active bots out of the maximum;
- a **benchmark comparison** — the orchestrator's benchmark return and the excess return
  since its first snapshot — when the benchmark has usable stored closes, omitted otherwise;
- its **best and worst bot** by that day's P&L among its active bots, omitted when it has
  no active bot;
- the bots it **started** that day, each with its preset, tickers and capital, or that
  none were started;
- the bots **stopped** that day — whether by an orchestrator decision or by the bot's own
  drawdown kill-switch — each with its preset, tickers, stop reason and return on its
  allocated capital, or that none were stopped;
- the status of that day's **decision run**, or that no decision run happened that day.

Each of the started and stopped lists SHALL show at most five bots, summarising any
further bots as a count, so the notification stays within the channel's message limit.

This daily notification SHALL replace the individual daily notifications of the bots the
orchestrator deployed. It SHALL be best-effort: a silent no-op when no notification channel
is configured, and a notification failure SHALL NOT fail the snapshot job.

#### Scenario: Scheduled run notifies a summary

- **WHEN** a scheduled run deploys one bot and stops one bot
- **THEN** a notification SHALL name the orchestrator and both bots

#### Scenario: Manual run is silent

- **WHEN** a manual run completes
- **THEN** no notification SHALL be sent

#### Scenario: Daily P&L notification per active orchestrator

- **WHEN** the evening snapshot job runs for an active orchestrator with two active bots
  and a previous snapshot
- **THEN** one notification SHALL be sent for it with its value, day change against the
  previous snapshot, total return, free and allocated capital, active bots out of the
  maximum, its best and worst bot, the bots started and stopped that day, and that day's
  decision-run status

#### Scenario: First day compares against the capital pool

- **WHEN** an orchestrator's first snapshot is recorded
- **THEN** its day change SHALL be measured against its capital pool

#### Scenario: Daily notification names bots started and stopped today

- **WHEN** an orchestrator deployed one bot that morning and stopped another, and a third of
  its bots was stopped by its drawdown kill-switch during the day
- **THEN** the daily notification SHALL list the started bot with its preset, tickers and
  capital, and both stopped bots with their preset, tickers, stop reason (orchestrator or
  kill-switch) and return

#### Scenario: Long lists are capped

- **WHEN** more than five bots were started (or stopped) that day
- **THEN** the notification SHALL list five of them and summarise the rest as a count

#### Scenario: No decision run today

- **WHEN** no decision run happened for the orchestrator that day (for example on a
  weekly cadence)
- **THEN** the daily notification SHALL say that no decision run happened today

#### Scenario: Daily notification is best-effort

- **WHEN** the snapshot job runs while no notification channel is configured, or the
  channel fails
- **THEN** the snapshots SHALL still be recorded and the job SHALL NOT fail

### Requirement: Orchestrator on the dashboard

Each active bot orchestrator SHALL appear on the dashboard as **one** performance row of kind
orchestrator, labelled with the orchestrator's label, covering its free capital and all of
its bots; the bots it deployed SHALL NOT appear as rows of their own. The row's figures SHALL
be computed as the dashboard's per-session performance requirement defines for orchestrators.
Stopped and archived orchestrators SHALL NOT appear, like stopped bots and closed sessions.

#### Scenario: One dashboard row per active orchestrator

- **WHEN** the dashboard loads with one active orchestrator running two bots
- **THEN** it SHALL show a single orchestrator row labelled with the orchestrator's label

#### Scenario: Stopped orchestrator leaves the dashboard

- **WHEN** an orchestrator is stopped
- **THEN** neither it nor its bots SHALL appear as dashboard rows

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

### Requirement: Orchestrator researches recent developments

The orchestrator agent's instructions SHALL direct it, when it searches the web, to look for
material developments of the last 7 days relative to the briefing's date (for example management
changes, investigations, guidance changes, mergers), to include the current month and year in news
searches, to prefer the search results' top stories, to check each result's date and disregard
stale results, and to remember that company fiscal years differ from calendar years.

#### Scenario: Instructions carry the research guidance

- **WHEN** an orchestrator run builds its agent
- **THEN** the instructions SHALL contain the recent-developments research guidance and the run
  SHALL record the prompt version that includes it
