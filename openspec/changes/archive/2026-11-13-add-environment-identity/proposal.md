## Why

Cadence is meant to run as two deployments once real money is involved: a **QA** environment on
an Alpaca paper account and a **PRD** environment on a live account. Today an instance does not
know which environment it is, the UI never shows it, and paper vs live is only a configuration
flag (`ALPACA_PAPER`) that nothing verifies or displays. Two open browser tabs look identical, and a
single wrong setting could point a deployment at the wrong account without anyone noticing.

## What Changes

- New setting **`CADENCE_ENVIRONMENT`** (free text, default `QA`): the deployment's name (e.g. `QA`,
  `PRD`).
- Cadence **verifies the account type** against Alpaca instead of trusting the flag: it reads the
  account on the configured endpoint; if the keys are rejected there it checks the other endpoint
  (read-only), so live keys on a paper configuration (or the reverse) are detected as a
  **mismatch**. The result is cached briefly; the stub broker reports paper.
- New setting **`ALPACA_ALLOW_LIVE`** (default `false`): on a live account, orders are only sent when
  it is `true` (PRD configuration only).
- **Trading guard** in the single order path: every order (bots, AI portfolios, Admin actions) is
  refused with a clear reason when the account mismatches the configuration, or when the account
  is live and `ALPACA_ALLOW_LIVE` is not set. Reads, valuation and snapshots keep working; refused
  bot orders surface through the existing tick failure health.
- New endpoint **`GET /api/v1/system/environment`**: environment name, configured mode, verified
  account mode (`paper` / `live` / `unknown`), mismatch flag, whether trading is enabled and why
  not. No secrets.
- **Header badge on every page**, one colour per meaning: `QA · Paper` (neutral grey),
  `PRD · Live` (solid red — real money), an amber ⚠ warning `Account mismatch — trading blocked`
  or `Live — trading disabled` when trading is blocked, and a grey outlined `account unknown`
  while Alpaca can't be reached.
- `docker-compose.yml` and `.env.example` pass and document the two settings.
- No migration.

## Capabilities

### New Capabilities
- `deployment-environment`: environment identity, verified account mode, trading guard, and the
  header badge.

### Modified Capabilities
<!-- none — the guard sits inside the existing single order path without changing its contract -->

## Impact

- Backend: `config.py` (two settings), `broker/alpaca.py` (account-mode probe), new
  `cadence/environment.py` (resolver + cache + guard), `orders/gateway.py` (guard before the
  journal intent), new router `GET /system/environment`, schemas.
- Frontend: `components/layout/Header.tsx` (badge), API hook + types.
- Deploy config: `docker-compose.yml`, `.env.example`.
- Running two deployments (separate compose projects, databases, ports, cron) is a deployment
  matter and out of scope.
