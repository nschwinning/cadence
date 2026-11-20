## MODIFIED Requirements

### Requirement: Roles

The system SHALL define three roles: `viewer`, which may read their own data and the shared data
(the asset universe, watchlist, market data and catalogs); `trader`, which includes `viewer` and
may also perform every state-changing action on their own data; and `admin`, which includes
`trader` and may also use the Admin area, manage the shared asset data (adding and removing assets,
regenerating the universe evaluation, running asset recommendations into the universe or the
watchlist), and read every user's data. A user without any of these
roles SHALL have no access.

#### Scenario: Trader includes viewer

- **WHEN** a user holds only `trader`
- **THEN** every read allowed to `viewer` SHALL also be allowed to that user

#### Scenario: User without a role

- **WHEN** an authenticated user holds none of the three roles
- **THEN** every API request SHALL be refused with 403

#### Scenario: Admin manages the watchlist

- **WHEN** a `trader` asks to run an asset recommendation into the watchlist
- **THEN** the request SHALL be refused with 403

### Requirement: API authentication and authorization

When authentication is enabled, every API route SHALL require a bearer access token issued by the
`cadence` realm, verified against the realm's public signing keys, with the configured issuer, the
audience `cadence-api`, and an unexpired lifetime; otherwise the request SHALL be refused with 401.
Read requests (GET, HEAD) SHALL require `viewer`; all other methods SHALL require `trader`; every
route under `/api/v1/admin` and every route that changes the shared asset data (adding or deleting
an asset, regenerating the universe evaluation, starting an asset recommendation run) SHALL require
`admin`; a missing role SHALL be refused with
403. The
health route and the cron-triggered routes SHALL be exempt and keep their own protection (the
cron token). Authentication SHALL be enabled by default; disabling it SHALL be an explicit setting
that is logged as a warning at startup.

#### Scenario: No token

- **WHEN** a request to a portfolio list arrives without a bearer token
- **THEN** it SHALL be refused with 401

#### Scenario: Viewer cannot act

- **WHEN** a `viewer` asks to stop a bot
- **THEN** the request SHALL be refused with 403 and the bot SHALL keep running

#### Scenario: Trader cannot use the Admin area

- **WHEN** a `trader` asks to flatten orphan positions
- **THEN** the request SHALL be refused with 403

#### Scenario: Trader cannot change the universe

- **WHEN** a `trader` asks to add an asset to the universe
- **THEN** the request SHALL be refused with 403 and the universe SHALL be unchanged

#### Scenario: Expired or foreign token

- **WHEN** a token is expired, signed by another key, or issued for another audience or issuer
- **THEN** the request SHALL be refused with 401

#### Scenario: Cron keeps working

- **WHEN** the cron sidecar triggers the daily rebalance with a valid cron token and no bearer
  token
- **THEN** the request SHALL be accepted

#### Scenario: Every route is guarded

- **WHEN** the API's routes are enumerated
- **THEN** every route other than health and the cron-triggered routes SHALL refuse a request
  without a token

### Requirement: Role-aware interface

The web application SHALL show the Admin menu entry, the universe-management controls and the
watchlist's discover control only to `admin` users, SHALL hide or disable controls that change state for users without `trader`, and SHALL show a "You don't have
permission for this action" message when the API answers 403.

#### Scenario: Viewer sees no write controls

- **WHEN** a `viewer` opens the bots page
- **THEN** the build-a-bot control SHALL not be available

#### Scenario: Admin menu hidden

- **WHEN** a `trader` signs in
- **THEN** the navigation SHALL not show the Admin entry, and the assets page SHALL not offer
  adding or removing assets or regenerating the universe evaluation

#### Scenario: Watchlist discover hidden

- **WHEN** a `trader` opens the watchlist
- **THEN** the page SHALL not offer discovering new watchlist assets
