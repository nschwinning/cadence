## ADDED Requirements

### Requirement: Tick health in the overview

The overview SHALL include a tick-health summary for the strategy-bot tick: the time and counts
(processed, skipped, failed, reconciled, market open) of the most recent recorded tick and whether
it failed with its error; whether ticks are **stale** — the equity market is open and no tick has
been recorded for more than 15 minutes (or none at all); and the list of bots with a recorded
failure, each with its id, display name, consecutive failure count, latest failure time and error
message. The summary SHALL be independent of the dashboard range.

#### Scenario: Healthy ticks

- **WHEN** the market is open, the latest tick ran 3 minutes ago and no bot is failing
- **THEN** the summary SHALL report that tick, not stale, and no failing bots

#### Scenario: Ticks have stopped

- **WHEN** the market is open and the latest recorded tick is 40 minutes old
- **THEN** the summary SHALL report ticks as stale

#### Scenario: Closed market is never stale

- **WHEN** the market is closed and the latest tick is hours old
- **THEN** the summary SHALL NOT report ticks as stale

#### Scenario: Failing bots are listed

- **WHEN** one bot has failed its last two ticks
- **THEN** the summary SHALL list that bot with two consecutive failures and its error
