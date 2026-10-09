## Why

`alpaca_symbol` was introduced by migration `c4e7a1f9b2d3` as a nullable column with no backfill, and add-time Alpaca verification only populates it for assets added *after* that migration. Every pre-existing row still has `alpaca_symbol = NULL` — in the live universe, 16 of 117 assets. Because a null `alpaca_symbol` is treated as "not tradable on Alpaca" (by both the asset-list not-tradable badge and the AI universe panel's `unpriceable_listings`), those legacy rows are **falsely flagged**: the 16 include genuinely-tradable blue chips (AAPL, TSLA, NVDA, GOOGL, AMZN, META, JPM, V, JNJ, WMT, PG, MA) and crypto (BTC-USD, ETH-USD); only 2 (AIR.PA, TTE.PA) are genuinely foreign. A one-off backfill that resolves these rows against the brokerage clears the false positives and leaves only the truly-untradable listings flagged.

## What Changes

- Add a `backfill_alpaca_symbols(session, broker)` service helper in `assets/service.py` that, for every asset whose `alpaca_symbol` is NULL, looks the ticker up on the brokerage (`broker.get_asset(ticker, asset_class)`, asset class derived from category exactly as `add_asset` does) and stores the brokerage's canonical symbol when the brokerage lists it as tradable; rows the brokerage does not list / lists as not tradable are left NULL. It is **idempotent** and **fail-open** (a per-asset error is logged and skipped so one failure never aborts the pass) and returns the count of rows updated.
- Mirror the existing `backfill_fractionable(session, broker)` helper's shape and conventions exactly.
- The helper is invoked once post-deploy by the operator (same convention the fractional-sizing backfill used — a short one-off call), not wired to an endpoint, CLI, cron, or startup hook.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `assets`: add a requirement that the system can resolve and backfill the brokerage's canonical symbol for existing assets that lack one, so tradability is accurate for rows added before add-time verification existed.

## Impact

- Backend only: new helper + tests in `backend/src/cadence/assets/service.py` and `backend/tests/test_assets_service.py`.
- **No migration, no schema change** (the `alpaca_symbol` column already exists and is already nullable). Kept out of Alembic on purpose — migrations own schema, services own external I/O, so an unreachable brokerage can never fail a deploy.
- No API, no router, no frontend change. The not-tradable badge and AI panel become correct automatically once the data is backfilled.
- Out of scope: clearing/re-verifying already-populated (non-null) symbols; changing the badge or AI-panel logic; `fractionable` (its own backfill exists); any scheduling/cron.
- Verify gates: `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest`.
