## Context

- Compose publishes the frontend (5174 → Vite dev server, which proxies `/api` and `/health` to
  `backend:8000`), Postgres (5435) and LiteLLM (4000); the backend is not published.
- `db/init/01-create-litellm-db.sql` creates extra databases on a fresh volume only; the Pi's
  volume exists, so new databases are created by hand once.
- Cron triggers are POST routes guarded by `require_valid_cron_token` (`X-Cron-Token`).
- The frontend uses one axios instance (`api/client.ts`) and React Query.
- User decisions: Keycloak in compose; viewer / trader / admin; SPA with OIDC PKCE; LAN today,
  possibly public later; **Caddy** as the HTTPS entry point (found during apply: the PKCE flow
  needs `crypto.subtle`, which browsers only provide in secure contexts — HTTPS or localhost — so
  plain `http://<pi>:5174` cannot log in).
- Environments (`docs/environments.md`): DEV / QA / PRD each with its own checkout and `.env`;
  published ports are configurable; DEV mocks Alpaca.

## Goals / Non-Goals

**Goals:** every API route authenticated and role-checked; login for the web app; Keycloak
self-contained in the deployment; nothing that relies on "LAN only".

**Non-Goals:** per-user provider keys and data scoping (a later bring-your-own-keys change — see
decision 9); a public domain; replacing the Vite dev server; closing the published Postgres
and LiteLLM ports; per-user data ownership; recording which user performed an action (later);
API keys for scripts.

## Decisions

0. **Caddy entry point.** `caddy:2-alpine` service, `caddy/Caddyfile`:
   ```
   {$CADENCE_HOSTNAME} {
       tls internal                     # local CA; replace with a domain for Let's Encrypt
       handle /auth* { reverse_proxy keycloak:8080 }
       handle /api*  { reverse_proxy backend:8000 }
       handle /health { reverse_proxy backend:8000 }
       handle { reverse_proxy frontend:5173 }   # Vite dev server incl. HMR websocket
   }
   ```
   Published `${CADDY_HTTPS_PORT:-8443}:443`; `caddy_data` volume keeps the local CA (root
   certificate at `/data/caddy/pki/authorities/local/root.crt`, exported with `docker compose cp`
   and installed once per device). `CADENCE_HOSTNAME` is the Pi's hostname or IP the browser uses;
   `CADENCE_PUBLIC_URL=https://${CADENCE_HOSTNAME}:${CADDY_HTTPS_PORT}`. Frontend and backend
   ports are published on `127.0.0.1` only (host-local debugging), so the LAN reaches Cadence only
   through Caddy; Postgres and LiteLLM stay as they are (a PRD prerequisite). Vite's
   `server.allowedHosts` accepts `CADENCE_HOSTNAME` (Vite rejects unknown `Host` headers). Going
   public later: set `CADENCE_HOSTNAME` to the domain, publish 80/443 — Caddy obtains and renews
   certificates itself.
1. **Same origin under `/auth`.** Keycloak runs with `KC_HTTP_RELATIVE_PATH=/auth` behind Caddy, so
   browser, app and IdP share one origin (first-party cookies for silent renew).
   `KC_HOSTNAME=${CADENCE_PUBLIC_URL}/auth`, `KC_PROXY_HEADERS=xforwarded`, `KC_HTTP_ENABLED=true`
   (TLS terminates at Caddy), `KC_HEALTH_ENABLED=true`, heap `-Xms256m -Xmx512m`. Not published on
   its own port.
2. **Realm import** `keycloak/cadence-realm.json` (`start --import-realm`; skipped once the realm
   exists): `sslRequired: external` (HTTP allowed only from private addresses), registration off,
   brute-force detection on, password policy `length(12)`, access token 5 min, SSO idle 30 min /
   max 10 h; realm roles `viewer`, `trader` (composite of viewer), `admin` (composite of trader);
   no default role; client `cadence-web`: public, standard flow only, PKCE S256, redirect URI and
   web origin `${CADENCE_PUBLIC_URL}/*`, post-logout redirect the same; an audience mapper adding
   `cadence-api`. Redirect URIs come from `CADENCE_PUBLIC_URL`: if the realm import cannot
   substitute environment variables, a one-shot `keycloak-init` container sets them with
   `kcadm.sh` after Keycloak is healthy (verified during apply).
3. **Seeded admin** (`keycloak-init`, a one-shot container running `kcadm.sh` after Keycloak is
   healthy, which also applies the redirect URIs if the import can't): when
   `CADENCE_ADMIN_USERNAME` / `CADENCE_ADMIN_PASSWORD` are set and the realm attribute
   `cadenceAdminSeeded` is absent, create the user (enabled, email-verified off), set the password
   with `--temporary`, add the `admin` realm role, then set `cadenceAdminSeeded=true`. The attribute
   makes the seed one-time even if the user is later deleted. The Keycloak bootstrap admin
   (`KEYCLOAK_ADMIN`, master realm) is a different account and has no Cadence role.
4. **Backend** `cadence/auth.py` with `PyJWT[crypto]`: `PyJWKClient(OIDC_JWKS_URL)` (internal URL,
   cached keys, refetch on unknown `kid`); `jwt.decode(..., algorithms=["RS256"],
   audience=OIDC_AUDIENCE, issuer=OIDC_ISSUER)` where the issuer is the public URL the browser
   used. `AuthUser(sub, username, roles)` with the hierarchy expanded server-side as well
   (defence in depth if composites are edited).
5. **Enforcement** is one app-wide dependency, `authorize(request)`: skip when `AUTH_ENABLED` is
   false, for `/health`, and for routes whose dependencies include `require_valid_cron_token`
   (inspected on `request.scope["route"]`); otherwise require a token, then `admin` for paths under
   `/api/v1/admin` and for the universe-management routes (an explicit list in `auth.py`:
   `POST /api/v1/assets`, `DELETE /api/v1/assets/{asset_id}`,
   `POST /api/v1/assets/universe-evaluation/refresh`), `viewer` for GET/HEAD, `trader` for other
   methods. `401` carries
   `WWW-Authenticate: Bearer`. A test walks `app.routes` and asserts every non-exempt route answers
   401 without a token.
6. **Settings**: `AUTH_ENABLED=True`, `OIDC_ISSUER` (e.g.
   `http://cadence.local:5174/auth/realms/cadence`), `OIDC_JWKS_URL` (default
   `http://keycloak:8080/auth/realms/cadence/protocol/openid-connect/certs`), `OIDC_AUDIENCE=cadence-api`,
   `CADENCE_PUBLIC_URL`, `KEYCLOAK_ADMIN` / `KEYCLOAK_ADMIN_PASSWORD` (bootstrap only),
   `CADENCE_ADMIN_USERNAME` / `CADENCE_ADMIN_PASSWORD` (optional one-time seed).
7. **Frontend**: `oidc-client-ts` + `react-oidc-context`; `AuthProvider` (authority
   `${origin}/auth/realms/cadence`, client `cadence-web`, `InMemoryWebStorage`,
   `automaticSilentRenew`); an `AuthGate` that triggers `signinRedirect` when unauthenticated and
   strips the callback parameters; an axios request interceptor reading the current token and a
   response interceptor (401 → `signinRedirect`, 403 → a dismissible permission banner); a header
   user menu with Log out (`signoutRedirect`); `useRoles()` from the access token's
   `realm_access.roles` with the hierarchy; `<RequireRole>` wrapper for write controls and the
   Admin nav. `VITE_AUTH_ENABLED=false` (default in tests) grants every role, so existing tests
   keep working.
8. **Tests**: backend conftest disables auth by default; auth tests generate an RSA key pair, patch
   the JWKS client and mint tokens (valid / expired / wrong audience / wrong issuer / wrong key /
   per role).

9. **Forward compatibility with per-user accounts (bring your own keys).** A later change will move
   the provider keys (OpenAI, Serper/SerpAPI, Alpaca, Pushover, …) from server-wide settings to
   each user's account, which makes portfolios, bots, the order journal, reconciliation, the Admin
   comparison, the environment badge and the cron jobs per-user. This change prepares for it
   without doing it: the Keycloak `sub` is the stable user identifier; `authorize` stores the
   `AuthUser` on `request.state.user` and a `current_user` dependency exposes it to routes; nothing
   keys data or settings by user yet, and all keys stay server-wide.
   The asset universe is shared and managed by admins only (enforced already by this change). The
   later change must resolve one conflict: AI portfolios add discovered tickers to the shared
   universe during rebalances — with several users that must become admin-approved suggestions
   or be switched off.
   Shared jobs run on a **platform account** configured by an admin (in the application, stored
   encrypted), never on a user's keys: an AI key for the universe evaluation (the only paid shared
   job) and an Alpaca data key (ideally a free data-only paper account) for tradability checks,
   news headlines / sentiment (fetched once per ticker per day and cached) and the market clock;
   LiteLLM attributes their spend to a "platform" bucket. Free sources (yfinance, SEC EDGAR, local
   price-ML and sentiment scoring) need no key. Until that change the platform keys are the
   server-wide `.env` keys.
   That later change must also **migrate the existing data** — AI portfolios and their sessions,
   strategy bots, orchestrators, order-journal records, snapshots and the server-wide keys — to one
   chosen account (identified by its Keycloak `sub`, e.g. the seeded admin), so nothing is lost or
   orphaned when ownership is introduced.

## Risks / Trade-offs

- Keycloak adds ~0.5–0.8 GB RAM on the Pi (per environment; Caddy ~30 MB).
- The address changes to `https://<pi>:<port>`; until Caddy's root certificate is installed on a
  device, its browser warns once.
- Tokens in memory: a page reload re-authenticates silently through the Keycloak session (no
  visible login while the SSO session lives).
- Tightly coupled to the public URL: changing the hostname means updating `CADENCE_PUBLIC_URL` /
  `OIDC_ISSUER` (and the client's redirect URIs).
- Enabling by default locks out a deployment until Keycloak and a user exist — intended; the deploy
  steps cover it.

## Migration Plan

Try it on DEV first; QA gets it with the next release branch.
1. `docker compose exec db createdb -U cadence keycloak` (existing volume; a fresh DEV volume gets
   it from `db/init`).
2. Set `CADENCE_HOSTNAME`, `CADDY_HTTPS_PORT`, `CADENCE_PUBLIC_URL`, `OIDC_ISSUER`, `KEYCLOAK_ADMIN`,
   `KEYCLOAK_ADMIN_PASSWORD` in `.env`.
3. Optionally set `CADENCE_ADMIN_USERNAME` / `CADENCE_ADMIN_PASSWORD` for the one-time seed.
4. `docker compose up -d --build`; export Caddy's root certificate and trust it on your devices;
   open `CADENCE_PUBLIC_URL`, log in with the seeded user and choose a new password
   (without the seed: open `/auth/admin` with the Keycloak admin, create your user, assign `admin`).
5. Rollback: `AUTH_ENABLED=false` and `VITE_AUTH_ENABLED=false`.

## Open Questions

None.
