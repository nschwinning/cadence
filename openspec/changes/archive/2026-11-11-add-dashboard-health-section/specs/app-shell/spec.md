## ADDED Requirements

### Requirement: Dashboard health section

The dashboard SHALL show a "Health" section, alongside the Broker account tile, that surfaces
everything needing the operator's attention without opening bot details or the Admin page:

- **Bot ticks**: the time of the latest tick and its processed / failed counts; a red warning
  when ticks are stale (the market is open and no tick has run for more than 15 minutes); a red
  warning when the latest tick itself failed, with its error; and a list of failing bots, each
  with its display name linking to the bot, its consecutive failure count and error message.
- **Account consistency**: counts of orphan positions, shortfalls, short positions and unresolved
  orders from the broker account overview, each non-zero count highlighted and the line linking to
  the Admin page; when all are zero it SHALL say the account matches Cadence's records. When the
  broker account cannot be read this line SHALL say so.

When nothing needs attention the section SHALL state that all is healthy. The section SHALL be
independent of the dashboard range and the equity-chart selection.

#### Scenario: All healthy

- **WHEN** ticks are current, no bot is failing and the account matches Cadence's records
- **THEN** the section SHALL show the latest tick and state that everything is healthy

#### Scenario: Stale ticks

- **WHEN** the overview reports ticks as stale
- **THEN** the section SHALL show a red warning that bot ticks have stopped running

#### Scenario: Failing bot is surfaced

- **WHEN** a bot has failed its last two ticks with a broker rejection
- **THEN** the section SHALL list it with a link to the bot, two consecutive failures and the
  rejection message

#### Scenario: Inconsistencies are counted

- **WHEN** the account has two short positions and one unresolved order
- **THEN** the section SHALL highlight two shorts and one unresolved order and link to the Admin
  page
