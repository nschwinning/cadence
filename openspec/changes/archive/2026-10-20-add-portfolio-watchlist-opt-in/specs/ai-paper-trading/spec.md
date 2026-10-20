## ADDED Requirements

### Requirement: Watchlist assets are a per-session opt-in frozen at build time

The system SHALL expose a per-session boolean option that controls whether the
session's candidate universe — the assets the AI may pick from on both the opening
allocation and every later rebalance — includes the user's `watchlist`-membership
assets in addition to the tradable `universe`-membership assets. The option SHALL
default to disabled, SHALL be chosen when the session is built, and SHALL be frozen
for the life of the session — the same build-time-frozen pattern as the stop-loss,
risk-guardrail, learning-feedback, and company-fundamentals options — so it SHALL
NOT be changeable after build. When the option is enabled, the candidate universe
SHALL be the union of `universe`-membership and `watchlist`-membership assets; when
it is disabled, the candidate universe SHALL remain the `universe`-membership assets
only (today's behavior). Watchlist-membership assets admitted by the option SHALL be
subject to the same downstream treatment as universe-membership assets — the
session's asset scope, stop-loss quarantine, the trend gate (when the session opted
in), eligibility, and the unexecutable-ticker exclusion — with no relaxation.
Sessions that predate this option SHALL be treated as having it disabled, leaving
their candidate universe unchanged. The build flow SHALL record the chosen value on
the session; the rebalance flow (which the opening allocation also runs through)
SHALL be the sole consumer that broadens the candidate universe.

#### Scenario: Option chosen at build and frozen

- **WHEN** an AI session is built with watchlist inclusion enabled
- **THEN** the session SHALL be persisted with watchlist inclusion enabled and that
  value SHALL remain fixed for the life of the session

#### Scenario: Default and pre-existing sessions exclude the watchlist

- **WHEN** an AI session is built without enabling watchlist inclusion, or a session
  predates the option
- **THEN** watchlist inclusion SHALL be disabled for that session and its candidate
  universe SHALL remain the universe-membership assets only, unchanged from today's

#### Scenario: Opening allocation honors the frozen option

- **WHEN** a session built with watchlist inclusion enabled runs its opening
  allocation (an initial rebalance)
- **THEN** the candidate universe presented to the AI SHALL include the session's
  watchlist-membership assets, subject to the session's asset scope and the usual
  quarantine and trend gates

## MODIFIED Requirements

### Requirement: Read paper-trading session data

The system SHALL let a client list paper-trading sessions and read a session's trades, runs, positions, its AI-portfolio events, and its daily portfolio-value snapshots. A session returned to a client SHALL include the name of the portfolio it trades so the client can identify the session by portfolio; when the portfolio cannot be resolved the name SHALL be absent (null) rather than causing an error. A session returned to a client SHALL include the benchmark it is compared against. A session returned to a client SHALL include the identifier of the AI model it runs on. A session returned to a client SHALL include its asset scope — whether it trades stocks only, crypto only, or both. A session returned to a client SHALL include its stop-loss configuration: whether the automatic stop-loss is enabled and, when enabled, its threshold percentage. A session returned to a client SHALL include its company-fundamentals configuration: whether company fundamentals are enabled. A session returned to a client SHALL include its watchlist-inclusion configuration: whether its candidate universe includes watchlist-membership assets. A session returned to a client SHALL include its risk-guardrail configuration: whether the risk guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage. A session returned to a client SHALL include its contributed capital (the sum of its recorded capital contributions, equal to its allocated capital). An AI-portfolio event returned to a client SHALL include the AI's reasoning output and its persisted research transcript. A trade, closed position, or run returned to a client SHALL include the reference to the AI-portfolio event that produced it, when present. A session's value history SHALL be returned ordered oldest snapshot first, and each snapshot in the returned history SHALL carry the value of a buy-and-hold of the benchmark that receives the session's capital contributions on their effective dates — each contribution buying benchmark units at that date's benchmark price — so the benchmark line starts at the session's first contribution on the first snapshot date and steps up by each later contribution; for a session with a single contribution this is equivalent to a buy-and-hold of the allocated capital rebased to the first snapshot date. When the benchmark has no stored price on or before a snapshot's date, that snapshot's benchmark value SHALL be absent (null) rather than causing an error.

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

#### Scenario: Session reports its model

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include the identifier of the AI model it runs on

#### Scenario: Session reports its asset scope

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include its asset scope (stocks, crypto, or both), defaulting to both when no explicit scope was recorded

#### Scenario: Session reports its stop-loss configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its automatic stop-loss is enabled and, when enabled, its threshold percentage

#### Scenario: Session reports its fundamentals configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its company fundamentals are enabled, defaulting to disabled when no explicit setting was recorded

#### Scenario: Session reports its watchlist-inclusion configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its candidate universe includes watchlist-membership assets, defaulting to disabled when no explicit setting was recorded

#### Scenario: Session reports its guardrail configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its risk guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage

#### Scenario: Session reports its contributed capital

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include its contributed capital, equal to the sum of its recorded capital contributions (its allocated capital)

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
- **THEN** the system SHALL return the session's daily value snapshots ordered oldest first, each with its date, total value, cash value, positions value, day's profit and loss, and the contribution-aware rebased benchmark value as of that date

#### Scenario: Benchmark line reflects a later capital contribution

- **WHEN** a client requests the value history of a session that received a capital contribution after it started
- **THEN** each snapshot's benchmark value on or after the contribution's effective date SHALL include benchmark units bought with the contributed amount at that date's benchmark price, so the benchmark line steps up by the contribution rather than ignoring it

#### Scenario: Benchmark price missing for a date

- **WHEN** a client requests a session's value history and the benchmark has no stored price on or before a snapshot's date
- **THEN** the system SHALL return that snapshot with the benchmark value absent rather than failing the request
