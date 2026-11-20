## Why

Cadence now authenticates users (Keycloak) but all data is still global: every signed-in user sees
and can act on every portfolio, bot and orchestrator. Before provider keys can move into user
accounts (bring-your-own-keys), data needs owners — and the data that exists today must end up in
your account, not orphaned.

## What Changes

- **Local user accounts**: a `users` table (internal id, Keycloak subject `sub`, username, last
  sign-in), created on a user's first authenticated request and found by `sub` afterwards.
  Ownership references the internal id, so Cadence data is not tied to Keycloak internals.
- **Owners on the ownership roots**: `portfolios`, `ai_portfolio_events` (a build event exists
  before its portfolio), `bot_orchestrators`, `bot_sessions` (an orchestrator-deployed bot gets its
  orchestrator's owner) and `broker_orders.account_user_id` (the account an order trades for,
  including Admin-area orders). Everything recorded under those (sessions, positions, trades, runs,
  snapshots, value history, orchestrator runs) inherits ownership through its parent.
- **Shared, not owned**: asset universe and watchlist, market data, indicators, price-ML,
  benchmarks, prompts, asset recommendation runs and the bot tick log.
- **Visibility**: users see and act on only their own data (other users' objects answer 404); the
  dashboard covers only their own data. **Admins read everything** (an "all users" toggle on the
  lists, owner shown on each object) but may only act on their own (403 otherwise).
- **Shared asset data is admin-managed** (by decision): starting an asset recommendation run —
  which adds to the universe or the watchlist — now needs `admin` on the backend (closing a gap
  where a trader could add assets through the API); the watchlist's Discover control is admin-only.
- **Migration**: one Alembic migration creates `users`, a **legacy owner** placeholder, the owner
  columns (backfilled to the legacy owner, then NOT NULL) and verifies consistency. The first sign-in
  of the Keycloak user named in `CADENCE_LEGACY_OWNER` links the placeholder permanently — your
  existing data becomes yours. Users signing in earlier get their own empty account.
- **Interim notice** (by decision): until bring-your-own-keys, all users trade on the one
  server-wide Alpaca account; the Admin page says so.
- With authentication disabled (local development, tests) every request acts as the legacy owner.

## Capabilities

### New Capabilities
- `user-accounts`: user records, ownership, visibility, migration of existing data, shared-account
  notice.

### Modified Capabilities
- `authentication`: roles describe own vs shared data and admin read-all; starting asset
  recommendation runs and watchlist discovery require `admin`.

## Impact

- Backend: new `users` model + migration; owner columns on five tables; `cadence/accounts.py`
  (resolve / create / link the current user, visibility helpers); every user-facing route for
  portfolios, AI portfolio, paper trading sessions, bots, orchestrators, dashboard and AI costs
  scoped by owner; create paths set the owner; orchestrator deploys inherit; order journal records
  the account; read schemas gain `owner` (username).
- Frontend: "All users" toggle and owner column for admins on the portfolio / bot / orchestrator
  lists; owner shown on detail pages; action controls hidden on other users' objects; watchlist
  Discover admin-only; Admin-page notice.
- Deploy: set `CADENCE_LEGACY_OWNER` in every environment's `.env` before deploying; on QA the
  migration assigns all existing data to you.
- Cron jobs, notifications, the Admin page's account comparison and all keys stay server-wide
  (bring-your-own-keys is the next change).
