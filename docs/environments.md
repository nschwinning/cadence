# Environments: DEV, QA, PRD

Cadence runs as up to three independent deployments. Each has its own checkout of the
repository and its own `.env`; the `.env` fully describes the environment — its name, Alpaca
mode, ports, keys, schedules and its compose project (`COMPOSE_PROJECT_NAME`). Different project
names keep containers, images, database volumes and networks apart, and separate checkouts let
each environment run a different version. Never change `COMPOSE_PROJECT_NAME` on an existing
environment: a new name means a new, empty database volume.

| | DEV | QA | PRD |
|---|---|---|---|
| Purpose | try new versions, break things | run released versions against the real market | trade real money |
| Brokerage | Alpaca **mocked** (`ALPACA_STUB=true`, no keys) | Alpaca **paper** account | Alpaca **live** account, `ALPACA_ALLOW_LIVE=true` |
| Header badge | `DEV · Mock` (blue) | `QA · Paper` (grey) | `PRD · Live` (red) |
| AI keys | separate low-budget key | normal key | separate key with its own budget |
| Daily AI jobs | parked (manual runs only) | on | on |
| Version | `main` | head of the current `release/YYYY.MM` branch | a tag `vYYYY.MM.N` on that branch |
| Host | the Pi, next to QA; stop it when idle | the Pi | own host preferred; never next to a running DEV |
| Data | disposable | kept | kept and backed up |
| Directory | `~/apps/cadence-dev` | `~/apps/cadence` | `~/apps/cadence-prd` |
| `COMPOSE_PROJECT_NAME` | `cadence-dev` | `cadence` | `cadence-prd` |
| Address (Caddy HTTPS) | `https://<pi>:9443` | `https://<pi>:8443` | `https://<domain>` |
| Published ports (db / LiteLLM; backend / frontend on 127.0.0.1 only) | 5436 / 4001; 8003 / 5175 | 5435 / 4000; 8002 / 5174 | only the HTTPS entry point |

The environment and its verified account type are always visible in the header badge
(`GET /api/v1/system/environment`). A mismatch between the configured and the real Alpaca
account, or a live account without `ALPACA_ALLOW_LIVE=true`, blocks every order.

## Branching and promotion

1. Everything merges to `main`; DEV runs `main`.
2. When `main` is good on DEV, cut `release/YYYY.MM` from it; QA switches to that branch.
3. Fixes found on QA are committed on the release branch (QA picks them up) and merged back to
   `main`. No new features on a release branch.
4. Production release: tag the exact release-branch commit QA has been running
   (`git tag -a vYYYY.MM.N`). Tags are immutable; PRD checks out tags only.
5. Hotfix: fix on the release branch → QA → next tag `vYYYY.MM.N+1` → PRD.
6. Next cycle: cut a new release branch from `main`; QA moves to it; the old branch ends once PRD
   has moved on.

Lockfiles (`backend/uv.lock`, `frontend/package-lock.json`) make the same commit rebuild the same
software. Database migrations run when the backend starts, so PRD runs exactly the migrations QA
already ran on that release; test risky migrations on QA against a copy of PRD data first.

## HTTPS and login

Each environment is reached only through its Caddy HTTPS entry point (`CADENCE_HOSTNAME`,
`CADDY_HTTPS_PORT`, `CADENCE_PUBLIC_URL` in `.env`). Caddy routes `/auth` to Keycloak, `/api` and
`/health` to the backend and everything else to the frontend; the frontend and backend ports
are bound to `127.0.0.1` (host-local debugging only). HTTPS is required: the login (OIDC
authorization code + PKCE) needs browser APIs that only exist on HTTPS pages.

**Trust Caddy's certificate (once per device and environment).** Caddy issues certificates from
its own local certificate authority, kept in the `caddy_data` volume:

```sh
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./cadence-<env>-root.crt
```

`CADENCE_HOSTNAME` may be a host name (e.g. `raspberrypi.local`) or the Pi's IP address. An IP
avoids depending on `.local` name resolution (and its IPv6 quirks); give the Pi a fixed address
in your router then (a DHCP reservation), because the certificate and Keycloak's allowed
addresses are tied to it. Changing `CADENCE_HOSTNAME` on an existing environment also requires
updating the `cadence-web` client's redirect URIs and web origins in Keycloak (realm import runs
only on the first start) — on DEV simply recreate it with `docker compose down -v`.

Install that file as a trusted root certificate on each device (macOS: Keychain Access → System →
import, set "Always Trust"; iOS: open it, then Settings → General → About → Certificate Trust
Settings; Windows: "Trusted Root Certification Authorities"). Until then the browser warns once.
Do not delete `caddy_data`, or every device has to trust a new certificate.

**Users and roles (Keycloak realm `cadence`).** `viewer` reads; `trader` also acts on
portfolios, bots and orchestrators; `admin` also uses the Admin page and manages the shared asset
data (universe, watchlist discovery, asset recommendations). New users get no role until one is assigned. Set `CADENCE_ADMIN_USERNAME` /
`CADENCE_ADMIN_PASSWORD` before the first start to have your admin created once (you choose a new
password at the first login); otherwise create users in the Keycloak admin console
(`<CADENCE_PUBLIC_URL>/auth/admin`, logging in with `KEYCLOAK_ADMIN`). Each environment has its
own Keycloak and users.

**Data ownership.** Every portfolio, paper-trading session, AI run, bot and orchestrator
belongs to one user. Users see and change only their own; admins can also view everyone's (the
"All users" switch on the lists) but cannot change other users' objects. The asset universe and
watchlist are shared. All users still trade on the one Alpaca account configured in `.env` until
per-user keys arrive (the Admin page says so).

Data created before accounts existed belongs to a *legacy owner*. Set `CADENCE_LEGACY_OWNER` to
your Keycloak username **before** deploying the release that introduces ownership; the migration
assigns all existing data to the legacy owner, and your first login links it to you (once). Deploy
order: set `CADENCE_LEGACY_OWNER` in `.env` → deploy (migrations run) → log in as that user first.
Anyone else logging in first just gets a new, empty account. Without auth (`AUTH_ENABLED=false`)
every request acts as the legacy owner.

**Existing database volume** (QA): create Keycloak's database once before the first start with
it — `docker compose exec db createdb -U cadence keycloak`. A fresh volume (new DEV) gets it
automatically.

**Going public later:** point a domain at the host, set `CADENCE_HOSTNAME` to it, remove
`tls internal` from `caddy/Caddyfile` and publish ports 80/443 — Caddy then obtains and renews
publicly trusted certificates by itself.

## DEV

First time:

```sh
cd ~/apps
git clone git@github.com:nschwinning/cadence.git cadence-dev
cd cadence-dev
cp .env.dev.example .env      # fill in: hostname/URL, AI + search keys, cron token,
                              # Keycloak admin, optional Cadence admin seed
docker compose up -d --build --wait
```

Then trust DEV's Caddy certificate (see above) and open `https://<pi>:9443`.

- Update: `git pull && docker compose up -d --build --wait`
- Pause (keeps data): `docker compose stop` — resume with `docker compose start`
- Reset (wipes DEV's database): `docker compose down -v`

DEV's `.env` must never contain Alpaca keys. With the stub on, Cadence makes no Alpaca call at
all (orders, positions, quotes, market clock, tradability checks, bot bars and news), and without
keys nothing could reach a real account even by mistake. DEV adds roughly 1–1.5 GB of RAM while
running — stop it when you are not testing.

## QA

QA's `.env` sets `COMPOSE_PROJECT_NAME=cadence` (the name it has always used, so adding the line
changes nothing). QA follows the current release branch:

```sh
cd ~/apps/cadence
git fetch && git switch release/YYYY.MM && git pull --ff-only
docker compose up -d --build --wait
```

Moving QA to the next release is a deliberate change of the branch name. Never deploy QA from
`main`.

## PRD (not set up yet)

Same as QA in `~/apps/cadence-prd`, checking out a tag (`git checkout vYYYY.MM.N`) with
`ALPACA_PAPER=false`, the live keys and `ALPACA_ALLOW_LIVE=true`. Before PRD may trade real
money:

- Keycloak authentication with roles;
- HTTPS through the reverse proxy (a real certificate if it is reachable publicly);
- a production frontend build instead of the Vite dev server;
- no published database, LiteLLM or backend ports;
- database backups with a tested restore;
- a separate Pushover target (or a clear prefix);
- enough paper-trading time on QA for the release being promoted.
