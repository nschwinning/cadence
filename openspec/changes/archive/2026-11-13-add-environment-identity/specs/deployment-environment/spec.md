## ADDED Requirements

### Requirement: Environment identity

Each Cadence deployment SHALL have an environment name taken from the `CADENCE_ENVIRONMENT`
setting (default `QA`). The system SHALL report, without exposing any secret, the environment
name, the configured account mode (paper when `ALPACA_PAPER` is on, live otherwise), the verified
account mode (`paper`, `live` or `unknown`), whether the two disagree, whether trading is enabled,
and the reason when it is not.

#### Scenario: Paper QA deployment

- **WHEN** a deployment named `QA` is configured for paper and its keys are accepted by the paper
  endpoint
- **THEN** it SHALL report environment `QA`, configured and verified mode `paper`, no mismatch,
  and trading enabled

#### Scenario: Default name

- **WHEN** `CADENCE_ENVIRONMENT` is not set
- **THEN** the environment name SHALL be `QA`

### Requirement: Verified account mode

The system SHALL verify the account mode against the broker rather than trust the configuration:
it SHALL read the account on the configured endpoint, and when the broker rejects the
credentials there it SHALL read the account on the other endpoint, without placing or changing
anything. The verified mode SHALL be the endpoint whose read succeeded; when neither succeeds it
SHALL be `unknown`. A verified mode different from the configured mode SHALL be a mismatch. The
result SHALL be cached for a short period so checks do not call the broker on every request. The
stub broker SHALL report a paper account.

#### Scenario: Live keys on a paper configuration

- **WHEN** `ALPACA_PAPER` is on but the paper endpoint rejects the keys and the live endpoint
  accepts them
- **THEN** the verified mode SHALL be `live` and a mismatch SHALL be reported

#### Scenario: Broker unreachable

- **WHEN** neither endpoint can be read
- **THEN** the verified mode SHALL be `unknown` and no mismatch SHALL be reported

### Requirement: Trading guard

Every order the system submits, through the single order path, SHALL first pass the trading
guard. The guard SHALL refuse the order, with a reason naming the cause, when the verified account
mode mismatches the configuration, or when the verified mode is live and `ALPACA_ALLOW_LIVE` is
not set. A refused order SHALL NOT be recorded in the order journal or sent to the broker, and
SHALL fail as an order error so its caller records the failure as for any rejected order.
Reading accounts, positions and prices, valuation and snapshots SHALL NOT be affected.

#### Scenario: Mismatch blocks trading

- **WHEN** the verified mode mismatches the configuration and a bot tries to buy
- **THEN** the order SHALL be refused with the mismatch reason, nothing SHALL be journaled or
  sent, and the bot's tick failure SHALL be recorded

#### Scenario: Live account needs the explicit opt-in

- **WHEN** the account is verified live, matches the configuration, and `ALPACA_ALLOW_LIVE` is not
  set
- **THEN** every order SHALL be refused and trading SHALL be reported disabled with that reason

#### Scenario: Live PRD trades with the opt-in

- **WHEN** the account is verified live, matches the configuration, and `ALPACA_ALLOW_LIVE` is set
- **THEN** orders SHALL be submitted as usual

#### Scenario: Unknown mode does not block

- **WHEN** the verified mode is `unknown` because the broker cannot be reached
- **THEN** the guard SHALL NOT refuse orders on that ground (the broker call itself fails)

### Requirement: Environment badge in the application header

Every page SHALL show an environment badge in the application header with the environment name
and the verified account mode. Each state SHALL have its own colour so it can be told apart by
colour alone: a neutral (grey) badge for a paper account (e.g. `QA · Paper`); a solid red badge
for a live account with trading enabled (e.g. `PRD · Live`) — red is reserved for real money; an
amber warning badge with a warning icon when trading is blocked, by a mismatch (`Account mismatch
— trading blocked`) or by the missing live opt-in (`Live — trading disabled`); and a grey outlined
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
