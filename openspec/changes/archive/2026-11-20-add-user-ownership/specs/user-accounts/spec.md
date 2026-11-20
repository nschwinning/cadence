## ADDED Requirements

### Requirement: User accounts

The system SHALL keep a user record for every person who signs in, with an internal identifier,
the identity provider's subject identifier (the stable link to the Keycloak account) and the
username. The first authenticated request of a Keycloak account without a record SHALL create
one; later requests SHALL find it by the subject identifier, so a changed username does not
create a second account. Ownership SHALL refer to the internal identifier, never to the identity
provider's identifier directly.

#### Scenario: First sign-in creates the account

- **WHEN** a Keycloak user signs in to Cadence for the first time
- **THEN** a user record SHALL be created and linked to that user's subject identifier

#### Scenario: Renamed user keeps their data

- **WHEN** a user whose username was changed in Keycloak signs in again
- **THEN** the same user record SHALL be found by the subject identifier and their data SHALL
  remain theirs

### Requirement: Owned data

Each AI portfolio, AI-portfolio job event, strategy bot and bot orchestrator SHALL belong to
exactly one user, set to the signed-in user when it is created. A bot deployed by an orchestrator
SHALL belong to the orchestrator's owner. Every record in the order journal SHALL name the user
whose account it trades for: the owner of the bot or AI portfolio it belongs to, or the
administrator who placed an Admin-area order. Data recorded under an owned object (sessions,
positions, trades, runs, snapshots, value history, orchestrator runs) SHALL belong to that
object's owner. The asset universe, watchlist, market data, technical indicators, price-ML
signals, benchmarks, prompts, asset recommendation runs and the bot tick log SHALL remain shared.

#### Scenario: Created data belongs to its creator

- **WHEN** a trader builds a bot
- **THEN** the bot SHALL belong to that trader

#### Scenario: Orchestrator bots follow the orchestrator

- **WHEN** an orchestrator owned by a user deploys a bot
- **THEN** the bot SHALL belong to that user

### Requirement: Data visibility

A user SHALL see and act on only their own data: lists SHALL contain only their own objects,
and reading or acting on another user's object SHALL answer as if it did not exist (404). The
dashboard's figures SHALL cover only the user's own data. An `admin` SHALL additionally be able
to read every user's data — lists offer an "all users" view and each object shows its owner — but
SHALL be refused (403) when acting on another user's object.

#### Scenario: Other users' objects are invisible

- **WHEN** a trader lists bots or opens the address of another user's bot
- **THEN** the list SHALL not contain it and opening it SHALL answer 404

#### Scenario: Admin reads all, acts on own

- **WHEN** an admin opens another user's portfolio and asks to rebalance it
- **THEN** the portfolio SHALL be shown with its owner, and the rebalance SHALL be refused with 403

#### Scenario: Dashboard covers own data

- **WHEN** two users each own a portfolio
- **THEN** each user's dashboard SHALL include only their own portfolio's value

### Requirement: Migration of existing data

When ownership is introduced, all existing portfolios, AI-portfolio job events, bots,
orchestrators and order-journal records SHALL be assigned to one legacy owner, so nothing is lost
or orphaned. The migration SHALL create the legacy owner as a user record not yet linked to any
Keycloak account; the first sign-in of the Keycloak user whose username equals the
`CADENCE_LEGACY_OWNER` setting SHALL link to it permanently (by subject identifier). Before
ownership is enforced the migration SHALL verify that every owned record has an owner and that
every orchestrator-deployed bot has its orchestrator's owner, and SHALL fail without changes
otherwise.

#### Scenario: Existing data becomes yours

- **WHEN** the migration has run and the user named in `CADENCE_LEGACY_OWNER` signs in
- **THEN** that user SHALL see every portfolio, bot and orchestrator that existed before

#### Scenario: Linking happens once

- **WHEN** the legacy owner has been linked and another account with the same username signs in
  later
- **THEN** that account SHALL get a new, empty user record and SHALL not see the legacy data

#### Scenario: Unlinked until the owner signs in

- **WHEN** another user signs in before the legacy owner
- **THEN** that user SHALL get their own empty account and SHALL not see the legacy data

### Requirement: Shared brokerage notice

Until users bring their own brokerage keys, every user's portfolios and bots SHALL trade on the
one server-wide Alpaca account; the Admin area SHALL state this.

#### Scenario: Notice on the Admin page

- **WHEN** an admin opens the Admin area
- **THEN** it SHALL state that all users currently share the configured Alpaca account
