## ADDED Requirements

### Requirement: Bot display name

Every bot session SHALL have a **display name** used consistently wherever a bot is named —
the Bots list, the bot detail header, its dashboard row, and its notification titles. The
display name SHALL be the session's label when it has one; otherwise it SHALL be the display
name of the preset it started from (or, without a preset, the strategy's display name)
followed by its traded set — the ticker when it trades one, otherwise the number of symbols
it trades. Internal strategy keys (such as `donchian_breakout`) SHALL NOT
be shown as a bot's name.

#### Scenario: Unlabelled preset bot

- **WHEN** a bot without a label was created from the Turtle Breakout (Algo 25) preset and
  trades MSFT
- **THEN** its display name SHALL be "Turtle Breakout (Algo 25) · MSFT" on the Bots list, its
  detail header and its notification titles

#### Scenario: Unlabelled custom bot

- **WHEN** a bot without a label and without a preset uses the Donchian range-breakout strategy
- **THEN** its display name SHALL use the strategy's display name, "Donchian Range Breakout",
  followed by its traded set

#### Scenario: Bot trading several symbols

- **WHEN** an unlabelled bot from the RSI Mean Reversion (Algo 16) preset trades three symbols
- **THEN** its display name SHALL be "RSI Mean Reversion (Algo 16) · 3 symbols"

#### Scenario: Labelled bot

- **WHEN** a bot has a label
- **THEN** its display name SHALL be that label

## MODIFIED Requirements

### Requirement: Dashboard performance adapter for bot sessions

The strategy-bots subsystem SHALL expose active **manually created** bot sessions to the dashboard in the
same per-session performance shape used for AI sessions, so the dashboard can render
them on shared axes without coupling to bot-specific persistence. Bot sessions deployed by a bot orchestrator SHALL NOT be exposed as rows of their own;
they are represented through their orchestrator. For each exposed
bot session over a selected range this SHALL include a stable identifier, its display
name, the allocated capital, the current
value **(cash plus all marked-to-market positions)**, the range profit/loss, fees,
realised and unrealised profit/loss, a value series windowed to the range, the
session's capital contributions, a since-inception benchmark buy-and-hold value computed
on the same basis as AI sessions, and a `kind` marker identifying the row as a bot.

#### Scenario: Bot row exposed in the shared performance shape

- **WHEN** the dashboard requests active-session performance for a range
- **THEN** each active bot session SHALL be returned in the same per-session
  performance shape as AI sessions, including its value series, contributions,
  since-inception benchmark value, and a `kind` marker identifying it as a bot

#### Scenario: Benchmark value basis matches AI sessions

- **WHEN** a bot session has a benchmark with priceable closes for its contributions
- **THEN** its since-inception benchmark value SHALL be computed on the same
  contribution-aware buy-and-hold basis used for AI sessions, so the two are
  directly comparable

#### Scenario: Orchestrator-deployed bots are not exposed

- **WHEN** the dashboard requests active-session performance while an orchestrator has an
  active bot
- **THEN** that bot SHALL NOT be returned as a row of its own
