## MODIFIED Requirements

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
- **THEN** the system SHALL return the already-running run and SHALL NOT start a
  concurrent run

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

## ADDED Requirements

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
