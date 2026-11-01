## ADDED Requirements

### Requirement: News sentiment is a per-session opt-in frozen at build time

The system SHALL expose a per-session boolean option that controls whether the
session's rebalance agent is informed of recent news sentiment for its candidates
and holdings. The option SHALL default to **disabled**, SHALL be chosen when the
session is built, and SHALL be frozen for the life of the session — the same
build-time-frozen pattern as the company-fundamentals, learning-feedback, stop-loss,
and risk-guardrail options — so it SHALL NOT be changeable after build. Sessions that
predate this option SHALL be treated as having news sentiment disabled, leaving their
behavior unchanged. The build flow SHALL record the chosen value on the session and
SHALL NOT itself fetch or score news.

#### Scenario: Flag chosen at build and frozen

- **WHEN** an AI session is built with news sentiment enabled
- **THEN** the session SHALL be persisted with news sentiment enabled, and that value
  SHALL remain fixed for the life of the session

#### Scenario: Default and pre-existing sessions disabled

- **WHEN** an AI session is built without enabling news sentiment, or a session
  predates the option
- **THEN** news sentiment SHALL be disabled for that session and its rebalance prompt
  SHALL be unchanged from today's

### Requirement: Rebalancing prompt includes news sentiment

The system SHALL provide a **news-sentiment** rebalance strategy as a per-session
**opt-in that defaults to off**, delivered as a new rebalance prompt version (per the
versioned-prompt requirement). When a session has opted into news sentiment **and**
is frozen on a prompt version at or after the sentiment-aware version, its rebalances
SHALL supply the agent with a per-ticker **news-sentiment advisory block** attached to
**both** the supplied buy candidates and the current holdings, so the agent can weigh
recent news tone when deciding what to buy and when deciding whether to sell, trim, or
hold. A session that did not opt in, or that is frozen on a prompt version predating
the sentiment-aware version, SHALL receive no sentiment block and SHALL behave exactly
as it did before this change. The sentiment-aware prompt version's instructions SHALL
describe the sentiment object **defensively** — weighing it when present and tolerating
its absence — so that an opted-out session frozen on that version reads correctly with
no sentiment attached.

The sentiment block for an asset SHALL carry only an **advisory tone signal** derived
from recent news over a trailing window: an aggregate tone leaning positive, neutral,
or negative, together with the number of articles it was derived from. The signal
SHALL be advisory tone, not a return forecast or a target weight. The prompt
instructions SHALL frame the signal as **long-only** guidance — positive tone
reinforcing a buy or hold, negative tone arguing to avoid or trim, **never** to open
a short.

When an asset has no usable sentiment — no recent news in the window, or the sentiment
source is unconfigured or unavailable at run time — the block SHALL render an explicit
**"sentiment unavailable"** marker for that asset rather than inventing a tone or
omitting the asset. Sentiment unavailability SHALL NOT fail the rebalance.

The prompt SHALL retain the existing rebalance constraints (long-only, target weights
sum to approximately 1.0, per-trade transaction-cost discipline, crypto handled with
around-the-clock tickers, discovery and web-search caps) and SHALL NOT change the AI
output schema — omitting a holding or giving it an allocation of ~0 still means
sell/exit.

#### Scenario: Opted-in session on the sentiment-aware prompt attaches the block

- **WHEN** a rebalance runs for a session that opted into news sentiment and is frozen
  on the sentiment-aware prompt version (or later)
- **THEN** the agent SHALL be presented with a per-ticker news-sentiment block on both
  the candidates and the current holdings

#### Scenario: Opted-out session receives no sentiment block

- **WHEN** a rebalance runs for a session that did not opt into news sentiment, even if
  it is frozen on the sentiment-aware prompt version
- **THEN** the agent SHALL be given the candidates and holdings without any sentiment
  block

#### Scenario: Older sessions receive no sentiment block

- **WHEN** a rebalance runs for a session frozen to a prompt version that predates the
  sentiment-aware version
- **THEN** the agent SHALL be given the candidates and holdings without any sentiment
  block, unchanged from that frozen version's behavior

#### Scenario: Unavailable sentiment is marked, not fabricated

- **WHEN** the sentiment block is assembled for an asset that has no recent news, or
  when the sentiment source is unconfigured or unavailable
- **THEN** that asset SHALL be shown with a "sentiment unavailable" marker and no
  invented tone, and the rebalance SHALL proceed

#### Scenario: Sentiment-aware prompt preserves the output contract

- **WHEN** the sentiment-aware rebalance prompt is used for a run
- **THEN** the agent SHALL still return long-only target allocations summing to
  approximately 1.0, with an omitted or ~0-weight holding meaning exit, unchanged from
  the prior prompt version's output schema

## MODIFIED Requirements

### Requirement: Read paper-trading session data

The system SHALL let a client list paper-trading sessions and read a session's trades, runs, positions, its AI-portfolio events, and its daily portfolio-value snapshots. A session returned to a client SHALL include the name of the portfolio it trades so the client can identify the session by portfolio; when the portfolio cannot be resolved the name SHALL be absent (null) rather than causing an error. A session returned to a client SHALL include the benchmark it is compared against. A session returned to a client SHALL include the identifier of the AI model it runs on. A session returned to a client SHALL include its asset scope — whether it trades stocks only, crypto only, or both. A session returned to a client SHALL include its stop-loss configuration: whether the automatic stop-loss is enabled and, when enabled, its threshold percentage. A session returned to a client SHALL include its company-fundamentals configuration: whether company fundamentals are enabled. A session returned to a client SHALL include its price-ML configuration: whether the price-ML signal is enabled. A session returned to a client SHALL include its news-sentiment configuration: whether news sentiment is enabled. A session returned to a client SHALL include its watchlist-inclusion configuration: whether its candidate universe includes watchlist-membership assets. A session returned to a client SHALL include its risk-guardrail configuration: whether the risk guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage. A session returned to a client SHALL include its contributed capital (the sum of its recorded capital contributions, equal to its allocated capital). A session returned to a client SHALL additionally include its **live current value**, its **realised profit/loss**, and its **unrealised profit/loss**, computed by marking the session's open positions to market at read time: the live current value SHALL be the session's net asset value (cash plus open positions valued at current market quotes, net of cumulative transaction fees); the realised profit/loss SHALL be the session's cumulative closed-lot realised profit/loss (gross of fees); and the unrealised profit/loss SHALL be the current mark-to-market gain or loss on the session's open positions. These three figures SHALL be present both when listing sessions and when reading a single session, computed from current quotes at request time rather than returned from a stale stored valuation. An AI-portfolio event returned to a client SHALL include the AI's reasoning output and its persisted research transcript. A trade, closed position, or run returned to a client SHALL include the reference to the AI-portfolio event that produced it, when present. A session's value history SHALL be returned ordered oldest snapshot first, and each snapshot in the returned history SHALL carry the value of a buy-and-hold of the benchmark that receives the session's capital contributions on their effective dates — each contribution buying benchmark units at that date's benchmark price — so the benchmark line starts at the session's first contribution on the first snapshot date and steps up by each later contribution; for a session with a single contribution this is equivalent to a buy-and-hold of the allocated capital rebased to the first snapshot date. When the benchmark has no stored price on or before a snapshot's date, that snapshot's benchmark value SHALL be absent (null) rather than causing an error.

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

#### Scenario: Session reports its price-ML configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its price-ML signal is enabled, defaulting to disabled when no explicit setting was recorded

#### Scenario: Session reports its news-sentiment configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its news sentiment is enabled, defaulting to disabled when no explicit setting was recorded

#### Scenario: Session reports its watchlist-inclusion configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its candidate universe includes watchlist-membership assets, defaulting to disabled when no explicit setting was recorded

#### Scenario: Session reports its guardrail configuration

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include whether its risk guardrails are enabled and, when enabled, the maximum percentage per asset, the maximum percentage per asset class, the minimum number of positions, and the maximum invested percentage

#### Scenario: Session reports its contributed capital

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include its contributed capital, equal to the sum of its recorded capital contributions (its allocated capital)

#### Scenario: Session reports its live value and profit/loss

- **WHEN** a client lists sessions or reads a single session
- **THEN** each returned session SHALL include its live current value (net asset value marked to current quotes, net of fees), its cumulative realised profit/loss, and its current unrealised profit/loss on open positions, computed from current quotes at request time rather than from a stale stored valuation

#### Scenario: Listed sessions are marked to market

- **WHEN** a client lists sessions while a session holds open positions whose quotes have moved since the last stored snapshot
- **THEN** that session's returned current value and unrealised profit/loss SHALL reflect the current quotes at request time, not the last stored snapshot

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
