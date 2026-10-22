# asset-recommendations Specification

## Purpose
Lets a user ask an AI to discover candidate tickers worth adding to the universe, validating each candidate through the same eligibility gate as manual additions, so the universe can grow without manual research.

## Requirements

### Requirement: Queue a recommendation run

The system SHALL accept a request to generate asset recommendations specifying
how many assets are wanted and optionally which categories to target. A request
SHALL also optionally specify a **target** of either `universe` (the default) or
`watchlist`. Supported categories are restricted to **stock** and **crypto**; a
request naming any other category SHALL be rejected. A **watchlist**-targeted
request SHALL be restricted to the **stock** category (watchlist fundamentals
come from equity filings); a watchlist request naming crypto SHALL be rejected.
The system SHALL create a run in a queued state and return immediately (202)
with the run's identifier, status, and target, without blocking on the AI. Only
one recommendation run SHALL execute at a time; if a run is already in flight,
the system SHALL return the in-flight run rather than starting a second.

#### Scenario: Queue a run

- **WHEN** a client requests recommendations with a valid requested count and
  supported categories (stock and/or crypto)
- **THEN** the system SHALL create a queued run targeting the universe (the
  default) and respond 202 with the run id and status

#### Scenario: Queue a watchlist run

- **WHEN** a client requests recommendations targeting the watchlist with a valid
  count and the stock category
- **THEN** the system SHALL create a queued watchlist-targeted run and respond
  202 with the run id, status, and target

#### Scenario: Reject an invalid request

- **WHEN** a client requests recommendations with an invalid count, a category
  other than stock or crypto, or a watchlist target with a non-stock category
- **THEN** the system SHALL respond 422 and SHALL NOT create a run

#### Scenario: A run is already in progress

- **WHEN** a client queues a run while another run is still executing
- **THEN** the system SHALL return the already-running run and SHALL NOT start a concurrent run

### Requirement: Execute a recommendation run and add eligible assets

The system SHALL progress a run through observable phases (queued → searching → validating → completed, or failed) and record the exact prompt used, the number of AI tool calls, and per-candidate outcomes. During validation each candidate SHALL be added through the standard asset-eligibility path; ineligible or duplicate candidates SHALL be recorded with their outcome and SHALL NOT be added. The run SHALL stop adding once the requested count of eligible assets is reached.

#### Scenario: Run completes and adds eligible candidates

- **WHEN** the AI returns candidates and validation runs
- **THEN** the system SHALL add eligible, non-duplicate candidates up to the requested count, record each candidate's outcome, and mark the run completed

#### Scenario: Run fails

- **WHEN** the AI call errors or times out
- **THEN** the system SHALL mark the run failed with a recorded reason and SHALL leave the universe unchanged except for candidates already validated

### Requirement: Poll recommendation run status

The system SHALL let a client list recommendation runs newest-first and fetch a single run's status by id. A run whose background worker has died without reaching a terminal phase SHALL be reported as failed.

#### Scenario: Poll until terminal

- **WHEN** a client fetches a run's status repeatedly
- **THEN** the system SHALL report the current phase and, once finished, a terminal phase with the per-candidate outcomes

#### Scenario: Unknown run

- **WHEN** a client fetches a run id that does not exist
- **THEN** the system SHALL respond 404

### Requirement: Offline stub mode

The system SHALL support an offline mode (selectable by configuration) in which recommendations are produced without any external AI or web-search calls, while still routing every candidate through the real eligibility validation.

#### Scenario: Stub mode enabled

- **WHEN** offline stub mode is enabled and a run is queued
- **THEN** the system SHALL generate candidates without external calls and validate them through the normal eligibility path

### Requirement: Recommendations exclude assets already in the universe

The recommender SHALL be given the set of tickers already present as assets
(whether in the universe or on the watchlist) and SHALL be instructed not to
propose any of them. The system SHALL still de-duplicate server-side against all
existing assets as a safety net, so a ticker already present is never added
twice regardless of what the agent returns or which target the run has.

#### Scenario: Existing tickers are excluded in the prompt

- **WHEN** a recommendation run starts while assets already exist
- **THEN** the prompt sent to the agent SHALL list those tickers as excluded and
  instruct the agent not to propose them

#### Scenario: A duplicate is never added

- **WHEN** the agent nonetheless proposes a ticker that already exists as an asset
- **THEN** the system SHALL skip it as a duplicate rather than adding it again

### Requirement: Execute a watchlist recommendation run for emerging companies

A watchlist-targeted run SHALL progress through the same observable phases
(queued → searching → validating → completed, or failed) and record the exact
prompt, AI tool-call count, and per-candidate outcomes as a universe run. Its
prompt SHALL explicitly instruct the agent to find **emerging companies from
promising sectors** — young, growing US-listed companies that are not yet mature
enough for the tradable universe.

During validation each candidate SHALL be added as a `watchlist` member. Unlike
a universe run, a watchlist run SHALL NOT reject a candidate for failing maturity
eligibility criteria (history or market capitalization) — admitting
emerging-but-ineligible names is the purpose of the watchlist. A watchlist
candidate SHALL still be required to clear the executability floor: it SHALL be a
supported **stock** category and SHALL be listed as tradable on the brokerage;
candidates failing that floor, or duplicates of any existing asset, SHALL be
recorded with their outcome and SHALL NOT be added. On successfully adding a
watchlist asset the system SHALL fetch and persist its SEC EDGAR fundamentals.
The run SHALL stop adding once the requested count of watchlist assets is reached.

#### Scenario: Watchlist run adds an emerging, ineligible company

- **WHEN** a watchlist run validates a brokerage-tradable US stock that fails the
  universe maturity criteria (for example too little history)
- **THEN** the system SHALL add it as a `watchlist` member with its eligibility
  flag false, fetch its fundamentals, and record the candidate's outcome

#### Scenario: Watchlist run rejects an untradable or non-stock candidate

- **WHEN** a watchlist candidate is not tradable on the brokerage, or is not of
  the stock category
- **THEN** the system SHALL record the candidate's outcome without adding it

#### Scenario: Watchlist run skips an already-tracked ticker

- **WHEN** a watchlist candidate is already present as an asset (in the universe
  or on the watchlist)
- **THEN** the system SHALL skip it as a duplicate and SHALL NOT add a second
  record

### Requirement: Select the AI model for a recommendation run

A recommendation-run request (universe or watchlist target) MAY specify the AI
`model` to run on, chosen from the shared AI model catalog. When the request omits
a model, the system SHALL use the configured default recommender model. A request
naming a model that is not in the catalog SHALL be rejected (422) without creating
a run. The system SHALL persist the resolved model on the run, SHALL execute the
run on that model, and SHALL report it on the run's status so every run records
which model produced its candidates. This applies identically to both the
universe (asset) recommender and the watchlist recommender, which share one agent.

#### Scenario: Run uses the selected model

- **WHEN** a client queues a recommendation run specifying a model that is in the
  catalog
- **THEN** the system SHALL create the run with that model, execute the agent on
  it, and report that model on the run's status

#### Scenario: Run defaults to the configured model

- **WHEN** a client queues a recommendation run without specifying a model
- **THEN** the system SHALL resolve the run's model to the configured default
  recommender model and report it on the run's status

#### Scenario: Unknown model is rejected

- **WHEN** a client queues a recommendation run naming a model that is not in the
  catalog
- **THEN** the system SHALL respond 422 and SHALL NOT create a run

#### Scenario: Watchlist run honours the selected model

- **WHEN** a client queues a watchlist-targeted run specifying a catalog model
- **THEN** the system SHALL execute the watchlist run on that model and report it
  on the run's status, the same as a universe run
