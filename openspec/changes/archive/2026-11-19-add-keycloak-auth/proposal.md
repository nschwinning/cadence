## Why

Cadence has no user authentication. Anyone who can reach the Pi can see every portfolio and bot,
and can build, rebalance, stop, deploy, flatten, restore or write off — including actions that
place real orders once a live PRD deployment exists. Cadence is LAN-only today but may be exposed
publicly later, so access control has to be designed for that case now.

## What Changes

- **HTTPS entry point (Caddy)**: a `caddy` service becomes the single way into Cadence:
  `https://<host>:<port>` (QA 8443, DEV 9443, configurable) routes `/auth` to Keycloak, `/api` and
  `/health` to the backend, and everything else to the frontend. It serves HTTPS with Caddy's own
  local certificate authority today (install its root certificate once per device) and gets
  Let's Encrypt certificates automatically once a public domain points at it. HTTPS is required:
  the PKCE login needs the browser's `crypto.subtle`, which only exists on HTTPS (or localhost).
  The frontend and backend ports are bound to `127.0.0.1`, so from the network Cadence is
  reachable only through Caddy.
- **Keycloak in compose**: a `keycloak` service (Keycloak 26, its own `keycloak` database on the
  existing Postgres, heap capped for the Pi), served under `/auth` on the same origin as the app
  (behind Caddy), with a versioned realm import: realm `cadence`,
  public client `cadence-web` (authorization code + PKCE S256), no self-registration, brute-force
  protection, a password policy, short-lived access tokens.
- **Optional seeded Cadence admin**: with `CADENCE_ADMIN_USERNAME` / `CADENCE_ADMIN_PASSWORD` set,
  the first realm setup creates that user with `admin` and a temporary password (changed at first
  login); a one-time seed, never repeated. No built-in default credentials anywhere. The Keycloak
  bootstrap admin (`KEYCLOAK_ADMIN`) only manages Keycloak and cannot use Cadence.
- **Three roles** (realm roles, composite): `viewer` (read everything) ⊂ `trader` (also every
  action that changes state: build/rebalance/stop/archive portfolios and bots, orchestrator
  actions, recommendations) ⊂ `admin` (also the Admin page — account comparison, flatten /
  restore / write-off / reconcile — and managing the asset universe: adding / removing assets and
  regenerating the universe evaluation). New users get no role until one is
  assigned.
- **Backend enforcement** for every `/api/v1` route: a valid Keycloak access token (signature via
  the realm's public keys, issuer, audience `cadence-api`, expiry) — `401` without one; reads need
  `viewer`, writes `trader`, everything under `/api/v1/admin` `admin` — `403` otherwise.
  Exempt: `/health`, and cron-triggered routes, which keep the `X-Cron-Token`. A test enumerates
  every route so no new route can slip through unguarded.
- **Frontend login** via OIDC authorization code + PKCE (`oidc-client-ts`): the whole app requires
  login; tokens are kept in memory and renewed silently; the API client sends the bearer token
  and re-logs in on `401`; the header shows the user with a **Log out** button; the Admin menu is
  hidden without `admin`, write controls are hidden or disabled without `trader`, and a `403` shows
  a "no permission" message.
- New settings `AUTH_ENABLED` (default **true**; `false` only for local development, logged as a
  warning), `CADENCE_HOSTNAME`, `CADDY_HTTPS_PORT`, `CADENCE_PUBLIC_URL`, `OIDC_ISSUER`,
  `OIDC_JWKS_URL`, `OIDC_AUDIENCE`, Keycloak admin bootstrap credentials; documented in
  `.env.example` and `.env.dev.example`.
- No Cadence data migration.

## Capabilities

### New Capabilities
- `authentication`: identity provider, roles, API enforcement, and the frontend login.

### Modified Capabilities
<!-- none: existing capabilities keep their behaviour for an authorised user -->

## Impact

- Compose: new `caddy` service (`caddy/Caddyfile`, `caddy_data` volume holding the local CA), new
  `keycloak` (+ one-shot `keycloak-init`) service, `db/init/02-create-keycloak-db.sql`,
  `keycloak/cadence-realm.json`; frontend and backend ports bound to `127.0.0.1`; Vite allowed
  hosts; backend + frontend env.
- Backend: `cadence/auth.py` (JWT validation, JWKS cache, role check), app-wide dependency,
  settings, `PyJWT[crypto]` dependency; tests run with auth disabled except the auth tests.
- Frontend: `oidc-client-ts` + `react-oidc-context`, auth provider, API interceptor, header user
  menu, role gating, 403 handling.
- **Prepares for bring-your-own-keys** (a later change moving provider keys and data to user
  accounts): the Keycloak user id is the stable identifier and the signed-in user is available to
  every route; keys and data stay server-wide for now.
- **Deploy step on the Pi** (existing database volume): `docker compose exec db createdb -U cadence
  keycloak`, set the new `.env` values (optionally the seeded admin), deploy, install Caddy's root
  certificate on your devices, open `https://<pi>:8443` and log in — or create users and assign
  roles in the Keycloak admin console (`/auth/admin`). The address changes from
  `http://<pi>:5174` to `https://<pi>:8443` (DEV: `https://<pi>:9443`).
- Not covered (needed before going public): a public domain (Caddy then obtains real certificates
  by itself), the Vite dev server serving the frontend, and the published Postgres (5435) and
  LiteLLM (4000) ports.
