## MODIFIED Requirements

### Requirement: Record sessions, trades, runs, and closed positions

The system SHALL persist, per paper-trading session, the executed trades (ticker, side, quantity, price, notional, signal type, order identity and status), a run entry per execution (counts and a trigger and status), the session's open positions in a ledger (per held ticker: quantity, weighted-average cost, and opened date), and closed positions with realized profit and loss when positions are exited. Every executed fill SHALL update the open-position ledger (a buy opens or increases an entry and re-computes its weighted-average cost; a sell reduces or removes it), and realized profit and loss SHALL be derived from the ledger entry's average cost and opened date. Each AI build or rebalance SHALL be recorded as an AI-portfolio event capturing the AI's output (its reasoning) and the actions taken, and SHALL also persist the run's research transcript: the web searches performed during the run and, for each, the query and the results the agent received (or a note when a search was not performed, e.g. the per-run search budget was exhausted). Each trade, each closed position, and each run produced by an AI build or rebalance SHALL record a reference to the AI-portfolio event that produced it; trades, closed positions, and runs not produced by an AI build or rebalance — such as automatic stop-loss runs or scheduled/manual scanner runs — SHALL leave this reference empty.

#### Scenario: Trades and run recorded on execution

- **WHEN** a build or rebalance places orders
- **THEN** the system SHALL record a trade per executed order, a run entry summarizing the execution, updated open-position ledger entries, and (for exits) closed positions with realized P&L

#### Scenario: Trades and closed positions reference their run

- **WHEN** an AI build or rebalance records a trade or a closed position
- **THEN** the recorded trade or closed position SHALL reference the AI-portfolio event that produced it

#### Scenario: Runs reference their producing AI event

- **WHEN** an AI build or rebalance records a run entry
- **THEN** the recorded run SHALL reference the AI-portfolio event that produced it

#### Scenario: Non-AI runs leave the event reference empty

- **WHEN** a run is recorded that was not produced by an AI build or rebalance — for example an automatic stop-loss run or a scheduled/manual scanner run
- **THEN** the recorded run SHALL leave the AI-portfolio event reference empty

#### Scenario: Research transcript persisted

- **WHEN** an AI build or rebalance reaches the agent and the agent performs web searches
- **THEN** the recorded AI-portfolio event SHALL persist each search's query and the results the agent received

#### Scenario: Research captured despite a mid-run failure

- **WHEN** an AI run fails after the agent has already performed one or more web searches
- **THEN** the recorded (failed) AI-portfolio event SHALL still persist the research captured before the failure

### Requirement: Read paper-trading session data

The system SHALL let a client list paper-trading sessions and read a session's trades, runs, positions, its AI-portfolio events, and its daily portfolio-value snapshots. A session returned to a client SHALL include the name of the portfolio it trades so the client can identify the session by portfolio; when the portfolio cannot be resolved the name SHALL be absent (null) rather than causing an error. A session returned to a client SHALL include the benchmark it is compared against. A session returned to a client SHALL include its stop-loss configuration: whether the automatic stop-loss is enabled and, when enabled, its threshold percentage. A session returned to a client SHALL include its risk-guardrail configuration: whether the risk guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage. An AI-portfolio event returned to a client SHALL include the AI's reasoning output and its persisted research transcript. A trade, closed position, or run returned to a client SHALL include the reference to the AI-portfolio event that produced it, when present. A session's value history SHALL be returned ordered oldest snapshot first, and each snapshot in the returned history SHALL carry the value of a buy-and-hold of the session's allocated capital in the session's benchmark as of that snapshot's date, derived from the stored benchmark price series and rebased so the benchmark equals the allocated capital on the session's first snapshot date. When the benchmark has no stored price on or before a snapshot's date, that snapshot's benchmark value SHALL be absent (null) rather than causing an error.

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
