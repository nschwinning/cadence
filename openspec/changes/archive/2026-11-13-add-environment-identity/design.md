## Context

`AlpacaBroker` picks `PAPER_BASE_URL` or `LIVE_BASE_URL` from `settings.ALPACA_PAPER`
(default true); `AccountInfo.is_paper` merely echoes the flag and is unused. Alpaca keys are
environment-specific: paper keys authenticate only against `paper-api.alpaca.markets`, live keys
only against `api.alpaca.markets` (401/403 otherwise). Every order goes through
`orders/gateway.OrderGateway` (architecture test), which journals an intent and then submits.
The app shell header is `components/layout/Header.tsx`. User decisions: explicit environment
name plus verified account mode; header badge only; mismatch blocks trading; live needs
`ALPACA_ALLOW_LIVE`.

## Goals / Non-Goals

**Goals:** each deployment knows and shows its name and real account mode; trading is refused on
a mismatch or an un-opted-in live account.

**Non-Goals:** deploying two instances (compose projects, DBs, cron); the tab title, Admin or
System-status display (not chosen); account-number display.

## Decisions

1. **Settings**: `CADENCE_ENVIRONMENT: str = "QA"`, `ALPACA_ALLOW_LIVE: bool = False`, passed through
   `docker-compose.yml` (`${CADENCE_ENVIRONMENT:-QA}`, `${ALPACA_ALLOW_LIVE:-false}`) and documented
   in `.env.example`.
2. **Probe**: `AlpacaBroker.probe_account_mode() -> Literal["paper","live","unknown"]` — `GET
   /v2/account` on the configured base URL; on 401/403 the same read on the other base URL; any
   success returns that endpoint's mode; network errors / both rejected → `unknown`. Read-only.
   `StubBroker` returns `"paper"`. The method is deliberately not added to the `Broker`
   protocol: several duck-typed test brokers implement it partially, so the resolver looks it up
   with `getattr` and treats a broker without a probe as `unknown` (never blocking). The cache
   key is `AlpacaBroker.credentials_fingerprint` (a one-way hash, in-process only).
3. **Resolver** (`cadence/environment.py`): `EnvironmentStatus(environment, configured_mode,
   account_mode, mismatch, trading_enabled, reason)`; `resolve_environment(broker, now)` caches the
   probe result per process for 5 minutes (`unknown` results only 30 seconds, so recovery is
   quick). `mismatch = account_mode != "unknown" and account_mode != configured_mode`.
   `trading_enabled = not mismatch and not (account_mode == "live" and not ALPACA_ALLOW_LIVE)`.
4. **Guard**: `OrderGateway` calls `environment.ensure_trading_allowed(broker)` before
   `journal.record_intent`; it raises `TradingDisabledError(OrderError)` with the reason. As an
   `OrderError` it is already handled by every caller (bot tick failure recording, AI run errors,
   Admin action messages); nothing is journaled, so no lease or reconciliation noise.
5. **Endpoint**: `GET /api/v1/system/environment` (no auth, like `/system/status`) returns the
   status; no keys or account numbers.
6. **Badge**: `useEnvironment()` (React Query, 5-minute refetch) in `Header.tsx`; a `role="status"`
   pill with a `title` tooltip carrying the reason; hidden until the first response. One colour per
   meaning (amber is already the app's warning colour, e.g. the dashboard account tile):
   paper → `bg-slate-100 text-slate-700`; live + trading enabled → `bg-red-600 text-white`
   (red = real money); blocked (mismatch / live without opt-in) → `bg-amber-100 text-amber-900
   ring-amber-300` with a ⚠ icon; unknown → `ring-1 ring-slate-300 text-slate-500`.

## Risks / Trade-offs

- The 5-minute cache means a key swap takes up to 5 minutes to show; a restart (how settings
  change anyway) clears it.
- If Alpaca ever accepted keys on both endpoints, the configured endpoint wins (checked first) —
  no false mismatch.

## Migration Plan

None. Existing deployments default to `QA` and, on paper keys, show `QA · Paper` with trading
unchanged. A PRD deployment sets `CADENCE_ENVIRONMENT=PRD`, `ALPACA_PAPER=false`, live keys and
`ALPACA_ALLOW_LIVE=true`.

## Open Questions

None.
