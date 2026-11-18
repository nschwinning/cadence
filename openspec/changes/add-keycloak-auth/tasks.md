## 0. HTTPS entry point

- [x] 0.1 `caddy` service + `caddy/Caddyfile` (`tls internal`, routes `/auth`, `/api`, `/health`, frontend), `caddy_data` volume, `CADDY_HTTPS_PORT` (QA 8443 / DEV 9443), `CADENCE_HOSTNAME`, `CADENCE_PUBLIC_URL`; frontend + backend ports bound to `127.0.0.1`; Vite `allowedHosts`; `.env.example`, `.env.dev.example`; `docs/environments.md` (HTTPS addresses, trusting the root certificate); verify `docker compose config` and, in the smoke test, HTTPS routing and the refused direct ports.

## 1. Keycloak

- [x] 1.1 `keycloak` service in compose (Keycloak 26, `/auth` behind Caddy, Postgres `keycloak` DB, heap cap, health), `db/init/02-create-keycloak-db.sql`; `.env.example`, `.env.dev.example`.
- [x] 1.2 `keycloak/cadence-realm.json` (realm, roles + composites, client with PKCE, audience mapper, policies); redirect URIs from `CADENCE_PUBLIC_URL` (env placeholder or `keycloak-init` with kcadm); verify with a JSON-structure test (roles/composites, PKCE, no registration).

- [x] 1.3 `keycloak-init` one-shot container (`kcadm.sh`): optional admin seed from `CADENCE_ADMIN_USERNAME` / `CADENCE_ADMIN_PASSWORD` (temporary password, `admin` role, `cadenceAdminSeeded` realm attribute guard) and redirect URIs if the import can't substitute them; verify in the compose smoke (seeded user must change password; restart does not recreate a deleted user; no settings → no user).

## 2. Backend

- [x] 2.1 Settings + `PyJWT[crypto]`; `cadence/auth.py` (JWKS client, token validation, roles with hierarchy); verify with pytest (valid / expired / wrong audience / issuer / key; role expansion).
- [x] 2.2 App-wide `authorize` dependency (stores `AuthUser` on `request.state.user`; `current_user` dependency for routes) (exemptions: disabled, `/health`, cron routes; viewer / trader / admin by method and path, admin for `/api/v1/admin` and the universe-management routes; 401 / 403); conftest disables auth by default; verify with pytest (no token 401; viewer GET ok, POST 403; trader admin 403; trader add-asset 403; admin ok; cron route with cron token ok; route walk test).
- [x] 2.3 Startup warning when `AUTH_ENABLED` is false.

## 3. Frontend

- [x] 3.1 `oidc-client-ts` + `react-oidc-context`; `AuthProvider` + `AuthGate`; API interceptors (bearer, 401 → login, 403 → banner); verify with vitest.
- [x] 3.2 Header user menu (name + Log out); `useRoles` + `<RequireRole>`; Admin nav and universe-management controls (assets page) gated to admin; write controls gated on the portfolio, AI portfolio, bots, orchestrators, recommendations, assets and admin pages; verify with vitest (viewer hides build/deploy controls, trader hides Admin, admin sees all; auth disabled grants all).

## 4. Verification

- [x] 4.1 Backend: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` (5435 test DB up, torn down afterwards).
- [x] 4.2 Frontend: `cd frontend && npm run typecheck && npx vitest run && npm run build`.
- [x] 4.3 Local compose smoke (DEV settings, stubbed Alpaca): Caddy serves HTTPS, Keycloak starts, realm imported, admin seeded, login → API call with token → role checks, direct ports refused from outside (documented manual steps); Docker cleaned up afterwards.
- [x] 4.4 `openspec validate add-keycloak-auth --strict` passes.
