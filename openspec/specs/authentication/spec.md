# authentication Specification

## Purpose

Control who can use Cadence and what they may do: a Keycloak identity provider behind a single HTTPS entry point, three roles (viewer, trader, admin), authentication and role checks on every API route (health and cron routes keep their own protection), and a login-gated, role-aware web application.

## Requirements

### Requirement: HTTPS entry point

The deployment SHALL expose Cadence to the network only through one HTTPS entry point on a
configurable host and port, which SHALL route `/auth` to the identity provider, `/api` and
`/health` to the backend, and all other paths to the web application. Without a public domain it
SHALL serve certificates from its own local certificate authority, whose root certificate SHALL
persist across restarts so devices need to trust it only once; with a public domain it SHALL obtain
publicly trusted certificates automatically. The web application and backend ports SHALL NOT be
reachable from other machines directly.

#### Scenario: Single HTTPS address

- **WHEN** a user opens the configured address (e.g. `https://<host>:8443`)
- **THEN** the web application, its API calls and the login SHALL all be served over HTTPS from
  that origin

#### Scenario: No direct access to internal ports

- **WHEN** another machine connects to the web application's or the backend's port directly
- **THEN** the connection SHALL be refused

#### Scenario: Root certificate kept

- **WHEN** the entry point restarts
- **THEN** it SHALL keep using the same local certificate authority

### Requirement: Identity provider

The system SHALL ship a Keycloak identity provider in its deployment, served under the path
`/auth` on the same origin as the application (behind the HTTPS entry point) and backed by its own
database. Its realm `cadence`
SHALL be created from a versioned import with a public client `cadence-web` that allows only the
authorization-code flow with PKCE (S256) and redirect URIs under the configured public URL;
self-registration SHALL be disabled, brute-force protection enabled and a password policy set.
Access tokens SHALL be short-lived and carry the audience `cadence-api` and the user's realm
roles. No account with a built-in default password SHALL exist.

When `CADENCE_ADMIN_USERNAME` and `CADENCE_ADMIN_PASSWORD` are configured, the system SHALL create
that user in the `cadence` realm with the `admin` role the first time the realm is set up, with the
password marked temporary so the user must choose a new one at first login; it SHALL record that
the seed happened and SHALL never create, overwrite or recreate the user afterwards. Without both
settings, no user SHALL be created.

#### Scenario: Realm imported on first start

- **WHEN** the deployment starts Keycloak with an empty Keycloak database
- **THEN** the `cadence` realm, the `cadence-web` client and the three roles SHALL exist

#### Scenario: Seeded admin must change the password

- **WHEN** `CADENCE_ADMIN_USERNAME` and `CADENCE_ADMIN_PASSWORD` are set and Keycloak starts for
  the first time
- **THEN** that user SHALL exist with the `admin` role and SHALL be required to set a new password
  at first login

#### Scenario: Seed happens once

- **WHEN** Keycloak restarts after the seed, even if the seeded user was deleted or its password
  changed
- **THEN** the user SHALL not be created or changed again

#### Scenario: No user without the seed settings

- **WHEN** the seed settings are not configured
- **THEN** the realm SHALL contain no users

#### Scenario: No self-registration

- **WHEN** someone opens the login page
- **THEN** it SHALL offer no way to register an account

### Requirement: Roles

The system SHALL define three roles: `viewer`, which may read everything; `trader`, which
includes `viewer` and may also perform every state-changing action except administration; and
`admin`, which includes `trader` and may also use the Admin area and manage the asset universe
(adding and removing assets, regenerating the universe evaluation). A user without any of these
roles SHALL have no access.

#### Scenario: Trader includes viewer

- **WHEN** a user holds only `trader`
- **THEN** every read allowed to `viewer` SHALL also be allowed to that user

#### Scenario: User without a role

- **WHEN** an authenticated user holds none of the three roles
- **THEN** every API request SHALL be refused with 403

### Requirement: API authentication and authorization

When authentication is enabled, every API route SHALL require a bearer access token issued by the
`cadence` realm, verified against the realm's public signing keys, with the configured issuer, the
audience `cadence-api`, and an unexpired lifetime; otherwise the request SHALL be refused with 401.
Read requests (GET, HEAD) SHALL require `viewer`; all other methods SHALL require `trader`; every
route under `/api/v1/admin` and every universe-management route (adding or deleting an asset,
regenerating the universe evaluation) SHALL require `admin`; a missing role SHALL be refused with
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

### Requirement: Frontend login and session

The web application SHALL require login before showing any page, using the OIDC
authorization-code flow with PKCE against the `cadence` realm. It SHALL keep tokens in memory,
renew them silently before they expire, send the access token as a bearer token on every API
request, and start a new login when the API answers 401. The header SHALL show the signed-in
user's name and a **Log out** action that ends the Keycloak session.

#### Scenario: Unauthenticated visit

- **WHEN** a user without a session opens any page
- **THEN** they SHALL be redirected to the Keycloak login and back to the page after signing in

#### Scenario: Log out

- **WHEN** a user selects Log out
- **THEN** the Keycloak session SHALL end and the next visit SHALL require login

### Requirement: Role-aware interface

The web application SHALL show the Admin menu entry and the universe-management controls only to
`admin` users, SHALL hide or disable controls that change state for users without `trader`, and SHALL show a "You don't have
permission for this action" message when the API answers 403.

#### Scenario: Viewer sees no write controls

- **WHEN** a `viewer` opens the bots page
- **THEN** the build-a-bot control SHALL not be available

#### Scenario: Admin menu hidden

- **WHEN** a `trader` signs in
- **THEN** the navigation SHALL not show the Admin entry, and the assets page SHALL not offer
  adding or removing assets or regenerating the universe evaluation
