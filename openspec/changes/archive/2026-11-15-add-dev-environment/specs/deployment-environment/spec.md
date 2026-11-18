## ADDED Requirements

### Requirement: Fully mocked brokerage

When the Alpaca stub is enabled, no part of the system SHALL contact Alpaca: orders, positions,
quotes, the market clock and tradability checks SHALL use the stub broker; strategy-bot bars SHALL
use the stub market data; and news headlines and news-sentiment retrieval SHALL return no news
without any network call, even when Alpaca keys are configured.

#### Scenario: Stubbed news makes no network call

- **WHEN** the Alpaca stub is enabled, Alpaca keys are configured, and a rebalance fetches headlines
- **THEN** no request SHALL be sent to the Alpaca News API and no headlines SHALL be attached

### Requirement: Side-by-side deployments on one host

The deployment SHALL allow several environments (e.g. QA and DEV) to run on the same host, each
from its own checkout of the repository with its own environment file, compose project, database
volume and network, so each environment can run a different version: every port the deployment publishes SHALL be configurable, with today's
values as defaults, and each environment file SHALL set its compose project name explicitly. An
example environment file for a DEV environment SHALL enable the Alpaca stub, contain no Alpaca
keys, name the environment `DEV`, set the compose project name `cadence-dev`, use different
published ports than the defaults, and document a separate low-budget AI key.

#### Scenario: Two projects on one host

- **WHEN** QA runs from its checkout with the default ports and DEV runs from a second checkout with
  the DEV example's ports
- **THEN** both SHALL run at the same time without port, volume or network conflicts

## MODIFIED Requirements

### Requirement: Environment identity

Each Cadence deployment SHALL have an environment name taken from the `CADENCE_ENVIRONMENT`
setting (default `QA`). The system SHALL report, without exposing any secret, the environment
name, the configured account mode (`mock` when the Alpaca stub is enabled, otherwise paper when `ALPACA_PAPER` is on and live when it
is off), the verified
account mode (`paper`, `live`, `mock` or `unknown`), whether the two disagree, whether trading is enabled,
and the reason when it is not.

#### Scenario: Paper QA deployment

- **WHEN** a deployment named `QA` is configured for paper and its keys are accepted by the paper
  endpoint
- **THEN** it SHALL report environment `QA`, configured and verified mode `paper`, no mismatch,
  and trading enabled

#### Scenario: Default name

- **WHEN** `CADENCE_ENVIRONMENT` is not set
- **THEN** the environment name SHALL be `QA`

#### Scenario: Mocked DEV deployment

- **WHEN** a deployment named `DEV` runs with the Alpaca stub enabled
- **THEN** it SHALL report environment `DEV`, configured and verified mode `mock`, no mismatch,
  and trading enabled

### Requirement: Verified account mode

The system SHALL verify the account mode against the broker rather than trust the configuration:
it SHALL read the account on the configured endpoint, and when the broker rejects the
credentials there it SHALL read the account on the other endpoint, without placing or changing
anything. The verified mode SHALL be the endpoint whose read succeeded; when neither succeeds it
SHALL be `unknown`. A verified mode different from the configured mode SHALL be a
mismatch, except that a verified `mock` account SHALL never be a mismatch (it cannot trade real
money). The
result SHALL be cached for a short period so checks do not call the broker on every request. The
stub broker SHALL report a `mock` account.

#### Scenario: Live keys on a paper configuration

- **WHEN** `ALPACA_PAPER` is on but the paper endpoint rejects the keys and the live endpoint
  accepts them
- **THEN** the verified mode SHALL be `live` and a mismatch SHALL be reported

#### Scenario: Broker unreachable

- **WHEN** neither endpoint can be read
- **THEN** the verified mode SHALL be `unknown` and no mismatch SHALL be reported

### Requirement: Environment badge in the application header

Every page SHALL show an environment badge in the application header with the environment name
and the verified account mode. Each state SHALL have its own colour so it can be told apart by
colour alone: a neutral (grey) badge for a paper account (e.g. `QA · Paper`); a solid red badge
for a live account with trading enabled (e.g. `PRD · Live`) — red is reserved for real money; an
amber warning badge with a warning icon when trading is blocked, by a mismatch (`Account mismatch
— trading blocked`) or by the missing live opt-in (`Live — trading disabled`); a blue badge for a mocked account (e.g. `DEV · Mock`); and a grey outlined
badge with the environment name and `account unknown` while the account mode is unknown. The
badge's tooltip SHALL give the reason when trading is disabled. The badge SHALL refresh
periodically.

#### Scenario: QA paper badge

- **WHEN** a user opens any page of a QA deployment on a paper account
- **THEN** the header SHALL show a neutral `QA · Paper` badge

#### Scenario: PRD live badge

- **WHEN** a user opens any page of a PRD deployment on a live account with trading enabled
- **THEN** the header SHALL show a solid red `PRD · Live` badge

#### Scenario: Mismatch warning

- **WHEN** the deployment reports a mismatch
- **THEN** the header SHALL show an amber `Account mismatch — trading blocked` warning with a
  warning icon, distinct in colour from the red live badge

#### Scenario: DEV mock badge

- **WHEN** a user opens any page of a DEV deployment running the Alpaca stub
- **THEN** the header SHALL show a blue `DEV · Mock` badge, distinct in colour from the paper,
  live and warning badges
