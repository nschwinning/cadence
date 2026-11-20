## Context

- Auth (`cadence/auth.py`): app-wide `authorize` puts `AuthUser(sub, username, roles)` on
  `request.state.user`; `get_current_user` dependency; disabled auth → no user.
- Ownership model agreed earlier (decision 9 of the Keycloak design): local `users` table linked by
  Keycloak `sub`; roots carry an owner; children inherit through FKs (all `ON DELETE CASCADE`);
  migration to one chosen account.
- Findings while planning: `recommendation_run` writes into the shared `assets` table (universe or
  watchlist bucket, `assets.membership`), so it is shared admin tooling, not owned data;
  `bot_tick_runs` is one global log per tick of the one account until bring-your-own-keys.
- User decisions: admins read all, act only on own; watchlist shared and admin-managed; allow other
  users before bring-your-own-keys with a notice; link existing data by username at first sign-in.

## Goals / Non-Goals

**Goals:** every owned object has an owner; users see only theirs; admins read all; existing data
ends up in your account; no orphaned rows.

**Non-Goals:** per-user keys, per-user Alpaca accounts, per-user cron runs or notifications
(bring-your-own-keys); transferring objects between users; per-user watchlists; resolving AI
discovery into the shared universe (bring-your-own-keys).

## Decisions

1. **`users`**: `id` UUID PK, `keycloak_sub` TEXT UNIQUE NULL, `username` TEXT NULL,
   `is_legacy_owner` BOOL (exactly one row may be true — partial unique index), `created_at`,
   `last_login_at`. The migration inserts the legacy owner (`is_legacy_owner=true`, `sub` and
   `username` NULL).
2. **Resolving the current user** — `accounts.current_account` dependency (needs the DB):
   - auth disabled → the legacy owner (tests, local development);
   - `sub` known → that user (`username` / `last_login_at` refreshed);
   - unknown `sub` and `username == CADENCE_LEGACY_OWNER` and the legacy owner is still unlinked →
     link it (`SELECT … FOR UPDATE`, set `sub` / `username`); linking happens once;
   - otherwise → create a new user.
   Returns `Account(user_id, username, is_admin)`.
3. **Owner columns**: `portfolios.owner_user_id`, `ai_portfolio_events.owner_user_id`,
   `bot_orchestrators.owner_user_id`, `bot_sessions.owner_user_id` (all FK `users.id`
   `ON DELETE RESTRICT`, indexed) and `broker_orders.account_user_id` (FK, NULL allowed only for
   legacy rows — backfilled anyway). Migration: add nullable → backfill legacy owner → verify
   (every root owned; every `bot_sessions` with `orchestrator_id` has the orchestrator's owner) →
   `SET NOT NULL` (journal included). Downgrade drops columns and the table.
4. **Scoping** in services, not ad-hoc in routes: list functions take `owner_ids: set[UUID] | None`
   (`None` = all, admin "all users"); detail and action paths load the object, then
   `accounts.ensure_can_read(account, owner_id)` (404 for others unless admin) /
   `ensure_can_act(account, owner_id)` (404 for others; 403 for admins on others'). Children
   (session runs, trades, value history, orchestrator runs, bot trades / KPIs / summary) check their
   root. List routes accept `scope=mine|all` (`all` admin only, else 403).
5. **Creation**: portfolio, AI build event, bot, orchestrator set `owner_user_id` from the account;
   the orchestrator's deploy path sets the bot's owner to the orchestrator's; journal writes set
   `account_user_id` from the owning bot / portfolio (looked up via the session for AI orders) or
   the acting admin (Admin-area orders); reconciliation never changes it.
6. **Dashboard / AI costs**: overview, metrics, tick health and AI-cost lists filter by the account;
   the Alpaca account tile stays the shared account (with the notice).
7. **Shared asset data admin-only**: `POST /api/v1/recommendations` joins `auth.UNIVERSE_ROUTES`
   (renamed `SHARED_ASSET_ROUTES`); the watchlist Discover control is wrapped in
   `RequireRole admin`.
8. **Read schemas** gain `owner: str | None` (username; `null` for an unlinked legacy owner, shown
   as "legacy owner") on portfolio, session, bot, orchestrator and run reads.
9. **Frontend**: `useRoles` admins get an "All users" switch on the Portfolios, Bots, Orchestrators
   and Runs lists (passes `scope=all`) plus an Owner column; detail pages show "Owner: …" when it
   isn't you and hide actions for objects you don't own; Admin page notice "All users currently
   trade on the configured Alpaca account."
10. **Tests**: conftest keeps auth disabled (requests act as the legacy owner, so existing tests
    keep working); ownership tests enable auth with two users (trader A, trader B) and an admin,
    covering lists, 404s, admin read / 403 act, creation ownership, orchestrator inheritance,
    journal account, legacy linking (by username, once; earlier users stay separate), and the
    migration on a scratch database (upgrade / downgrade / upgrade with data).

## Risks / Trade-offs

- Many routes change; a missed check would leak another user's data. Mitigation: a test that walks
  every owned-object route as user B against user A's objects and expects 404 / 403.
- Until bring-your-own-keys, users share the Alpaca account: positions of different users mix in
  one account; the Admin comparison stays account-wide.
- `CADENCE_LEGACY_OWNER` must be set before you first sign in after the migration, or you get an
  empty account (fix: admin SQL `UPDATE users …`, documented).

## Migration Plan

1. Set `CADENCE_LEGACY_OWNER=<your Keycloak username>` in the environment's `.env`.
2. Deploy; the backend runs the migration on start (all existing data → legacy owner).
3. Sign in — your account is linked and shows all existing data.
4. Rollback: the downgrade removes owners and `users` (data itself is untouched).

## Open Questions

None.
