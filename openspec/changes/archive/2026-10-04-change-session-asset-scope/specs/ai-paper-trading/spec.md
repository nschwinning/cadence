## MODIFIED Requirements

### Requirement: Read paper-trading session data

The system SHALL let a client list paper-trading sessions and read a session's trades, runs, positions, its AI-portfolio events, and its daily portfolio-value snapshots. A session returned to a client SHALL include the name of the portfolio it trades so the client can identify the session by portfolio; when the portfolio cannot be resolved the name SHALL be absent (null) rather than causing an error. A session returned to a client SHALL include the benchmark it is compared against. A session returned to a client SHALL include its asset scope — whether it trades stocks only, crypto only, or both. A session returned to a client SHALL include its stop-loss configuration: whether the automatic stop-loss is enabled and, when enabled, its threshold percentage. A session returned to a client SHALL include its risk-guardrail configuration: whether the risk guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage. An AI-portfolio event returned to a client SHALL include the AI's reasoning output and its persisted research transcript. A trade, closed position, or run returned to a client SHALL include the reference to the AI-portfolio event that produced it, when present. A session's value history SHALL be returned ordered oldest snapshot first, and each snapshot in the returned history SHALL carry the value of a buy-and-hold of the session's allocated capital in the session's benchmark as of that snapshot's date, derived from the stored benchmark price series and rebased so the benchmark equals the allocated capital on the session's first snapshot date. When the benchmark has no stored price on or before a snapshot's date, that snapshot's benchmark value SHALL be absent (null) rather than causing an error.

Each of a session's tabular list reads — its trades, runs, closed positions, and AI-portfolio events — SHALL support paging via a caller-supplied page size (limit) and a zero-based offset, returning at most the page size of rows starting at the offset within the read's existing ordering, together with the total number of rows recorded for that session and list. The AI-portfolio event read SHALL return its rows wrapped together with that total, in the same shape as the trades, runs, and closed-position reads (rather than a bare list without a total). Reads that source data for computed metrics rather than for a table — such as the closed-position profit-and-loss series behind the session KPIs — SHALL remain unpaged.

#### Scenario: Inspect a session

- **WHEN** a client requests a session's trades, runs, positions, or events
- **THEN** the system SHALL return the recorded data for that session

#### Scenario: Session identifies its portfolio

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include the name of the portfolio it trades

#### Scenario: Session reports its benchmark

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include the benchmark it is compared against

#### Scenario: Session reports its asset scope

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include its asset scope (stocks, crypto, or both), defaulting to both when no explicit scope was recorded

#### Scenario: Session reports its stop-loss configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its automatic stop-loss is enabled and, when enabled, its threshold percentage

#### Scenario: Session reports its guardrail configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its risk guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage

#### Scenario: Event includes reasoning and research

- **WHEN** a client reads an AI-portfolio event
- **THEN** the returned event SHALL include the AI reasoning output and the persisted research transcript

#### Scenario: Run reports its producing AI event

- **WHEN** a client reads a session's runs
- **THEN** each returned run SHALL include the reference to the AI-portfolio event that produced it when present, and SHALL omit it (null) for runs not produced by an AI build or rebalance

#### Scenario: Read a page of a session's list

- **WHEN** a client requests a session's trades, runs, closed positions, or AI-portfolio events with a page size and an offset
- **THEN** the system SHALL return at most that many rows starting at the given offset within the read's existing ordering, together with the total number of rows recorded for that session and list

#### Scenario: Event read reports its total

- **WHEN** a client reads a session's AI-portfolio events
- **THEN** the response SHALL contain the requested page of events wrapped together with the total number of events recorded for that session

#### Scenario: Offset beyond the end returns an empty page with the true total

- **WHEN** a client requests a page whose offset is at or beyond the number of recorded rows for one of these lists
- **THEN** the system SHALL return an empty page of rows together with the true total for that session and list

#### Scenario: Read session value history

- **WHEN** a client requests a session's value history
- **THEN** the system SHALL return the session's daily value snapshots ordered oldest first, each with its date, total value, cash value, positions value, day's profit and loss, and the rebased benchmark value as of that date

#### Scenario: Benchmark price missing for a date

- **WHEN** a client requests a session's value history and the benchmark has no stored price on or before a snapshot's date
- **THEN** the system SHALL return that snapshot with the benchmark value absent rather than failing the request

## ADDED Requirements

### Requirement: Change a session's asset scope

The system SHALL let a client change a paper-trading session's asset scope at any time to one of the supported scopes: stocks only, crypto only, or both. The new scope SHALL be persisted on the session so that all subsequent behavior keyed off scope — the assets an AI build or rebalance may target and discover, weekend crypto-rebalance selection, and weekend value-snapshot gating — honors the new scope. A request naming a scope outside the supported set SHALL be rejected and leave the session's scope unchanged. A request to change the scope of an unknown session SHALL fail as not found. Changing a session to the scope it already has SHALL be a successful no-op that neither liquidates holdings nor otherwise alters the session.

When the new scope EXCLUDES the asset class of one or more currently-held positions (a narrowing), the system SHALL immediately liquidate those now-out-of-scope positions as part of the scope change: it SHALL sell each out-of-scope position through the broker, record the resulting trades including the standard per-trade transaction cost (accumulated into the session's total fees like any other trade), close those positions in the session's ledger, and refresh the session's recorded value so the valuation reflects the sales. Positions whose asset class remains within the new scope SHALL NOT be sold. Widening the scope, or any scope change that excludes nothing currently held, SHALL liquidate nothing. When the scope change requires broker access but the broker is unavailable or unreachable, the system SHALL fail the request rather than record a scope change without performing the required liquidation.

#### Scenario: Change the scope

- **WHEN** a client changes an existing session's scope to another supported scope
- **THEN** the system SHALL persist the new scope and subsequent builds, rebalances, weekend crypto selection, and weekend snapshot gating SHALL use it

#### Scenario: Narrowing liquidates out-of-scope holdings

- **WHEN** a client narrows a session's scope so that a currently-held position's asset class is no longer in scope
- **THEN** the system SHALL sell that position through the broker, record the sale with the per-trade transaction cost accumulated into the session's total fees, close it in the ledger, and refresh the session's recorded value

#### Scenario: Widening liquidates nothing

- **WHEN** a client widens a session's scope, or changes it in a way that excludes no currently-held position
- **THEN** the system SHALL persist the new scope and SHALL NOT sell any position

#### Scenario: Unchanged scope is a no-op

- **WHEN** a client changes a session's scope to the scope it already has
- **THEN** the system SHALL succeed without liquidating any holdings or otherwise altering the session

#### Scenario: Unknown session

- **WHEN** a client changes the scope of a session id that does not exist
- **THEN** the system SHALL respond with a not-found error

#### Scenario: Scope outside the supported set

- **WHEN** a client changes a session's scope to a value that is not one of the supported scopes
- **THEN** the system SHALL reject the request and leave the session's scope unchanged

#### Scenario: Broker unavailable during a narrowing

- **WHEN** a narrowing scope change needs to liquidate out-of-scope holdings but the broker is unavailable or unreachable
- **THEN** the system SHALL fail the request rather than persist a scope change without performing the required liquidation
