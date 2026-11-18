## Context

`ALPACA_STUB` swaps the broker (`get_broker`), bot bars (`get_market_data`) and the system probe;
`AlpacaNewsSource` ignores it and calls Alpaca whenever keys exist. `AccountMode` is
`paper|live|unknown`; `StubBroker.probe_account_mode` returns `paper`. Compose publishes 5435 (db),
4000 (LiteLLM), 8002 (backend), 5174 (frontend) and sets no `container_name`, so a second project
name (`-p cadence-dev`) already isolates containers, volumes and networks. User decisions: DEV on
the Pi next to QA; real AI keys with a small budget.

## Goals / Non-Goals

**Goals:** a DEV deployment that cannot touch any Alpaca account and is clearly labelled.

**Non-Goals:** deployment scripts or automation; mocking AI or web search; Caddy (comes with the
Keycloak change); a realistic market simulator beyond the existing stub.

## Decisions

1. **News stub**: `AlpacaNewsSource.fetch_news` returns `[]` immediately when `ALPACA_STUB` is set
   (before the credential check), so headlines and sentiment are empty — no network call.
2. **`mock` mode**: `AccountMode = Literal["paper","live","mock","unknown"]`;
   `environment.configured_mode()` returns `mock` when `ALPACA_STUB`; `StubBroker.probe_account_mode`
   returns `mock`. A stub with `ALPACA_PAPER=false` is still `mock` (the stub never trades real
   money), so no mismatch and trading enabled; `ALPACA_ALLOW_LIVE` is irrelevant for `mock`.
3. **Badge**: `mock` → `{environment} · Mock`, `bg-sky-100 text-sky-800` (blue), no warning icon.
4. **Ports**: `"${DB_HOST_PORT:-5435}:5432"`, `"${LITELLM_HOST_PORT:-4000}:4000"`,
   `"${BACKEND_HOST_PORT:-8002}:8000"`, `"${FRONTEND_HOST_PORT:-5174}:5173"`.
5. **`.env.dev.example`**: mirrors `.env.example` with DEV values; AI schedules set to a never-firing
   cron expression (`0 0 31 2 *`) with a comment, bot tick / snapshot schedules left on (they hit
   the stub only); `REBALANCE_CRON_TOKEN` must still be set for the cron sidecar.
6. **One checkout per environment.** Each environment lives in its own directory
   (`~/apps/cadence-dev`, `~/apps/cadence` for QA, later `~/apps/cadence-prd`) with its own `.env`,
   which sets `COMPOSE_PROJECT_NAME` (`cadence-dev` / `cadence` / `cadence-prd`) so containers,
   images, volumes and networks never collide regardless of the directory name, and plain
   `docker compose up -d --build` works in each. A shared checkout would
   force the same code on every environment and is not supported.
7. **Docs**: `docs/environments.md` holds the environment plan below, the commands, the memory note,
   and that DEV's `.env` must never contain Alpaca keys.

## Environment plan

| | DEV | QA | PRD |
|---|---|---|---|
| Purpose | try new versions, break things | run released versions against the real market | trade real money |
| Brokerage | Alpaca **mocked** (`ALPACA_STUB=true`, no keys) | Alpaca **paper** account | Alpaca **live** account, `ALPACA_ALLOW_LIVE=true` |
| Badge | `DEV · Mock` (blue) | `QA · Paper` (grey) | `PRD · Live` (red) |
| AI keys | separate low-budget key | normal key | separate key with its own budget |
| AI schedules | parked (manual runs only) | on | on |
| Version | latest `main` | head of the current `release/YYYY.MM` branch | a tag `vYYYY.MM.N` on that branch |
| Host | Pi, next to QA; stopped when idle | Pi | own host preferred; at minimum not sharing with a running DEV |
| Data | disposable | kept | kept, backed up |
| Directory | `~/apps/cadence-dev` | `~/apps/cadence` (today's) | `~/apps/cadence-prd` |
| Ports (db / LiteLLM / backend / frontend) | 5436 / 4001 / 8003 / 5175 | 5435 / 4000 / 8002 / 5174 | none published except the HTTPS entry point |

**Branching and promotion:**
1. Everything merges to `main`; DEV runs `main`.
2. When `main` is good on DEV, cut `release/YYYY.MM` from it; QA switches to that branch.
3. Fixes found on QA are committed on the release branch (QA picks them up) and merged back to
   `main`; no new features on a release branch.
4. Production release: tag the exact release-branch commit QA has been running
   (`git tag -a vYYYY.MM.N`); tags are immutable, PRD checks out tags only.
5. Hotfix: fix on the release branch → QA → next tag `vYYYY.MM.N+1` → PRD.
6. Next cycle: cut a new release branch from `main`; QA moves to it; the old branch ends once PRD
   has moved on.
Lockfiles (`uv.lock`, `package-lock.json`) make the same commit rebuild the same software;
migrations run on start, so PRD runs exactly the migrations QA already ran on that release (test
risky ones on QA against a copy of PRD data first).

**PRD prerequisites** (none of which this change delivers): Keycloak auth with roles; Caddy with
HTTPS (real certificate if public); production frontend build instead of the Vite dev server; no
published database, LiteLLM or backend ports; database backups with a tested restore; a separate
Pushover target or prefix; and enough paper-trading time on QA for the release.

## Risks / Trade-offs

- Running DEV next to QA adds ~1–1.5 GB RAM (more with Keycloak later); stop DEV when idle.
- The stub's market is always open with deterministic prices — fine for flows, not for realism.

## Migration Plan

None for QA (defaults unchanged). DEV: copy `.env.dev.example` to `.env.dev`, fill the AI keys,
`docker compose -p cadence-dev --env-file .env.dev up -d --build`.

## Open Questions

None.
