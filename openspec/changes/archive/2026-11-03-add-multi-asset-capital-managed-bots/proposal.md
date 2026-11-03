## Why

Strategy bots today bind to exactly one equity, so expressing "trade these five stocks with at most $5,000 total" means deploying five independent single-asset bots — each funded separately, with no shared budget. Capital is not fungible across them: cash freed when one name exits cannot flow to another name that is signaling, and the combined deployment can silently exceed the capital the user actually intends to risk. Users want one bot that trades several equities (or the whole eligible universe) from a single, hard-capped capital pool, and sizes each position by risk rather than committing the same amount to every name.

## What Changes

- **BREAKING** A `BotSession` trades a **set** of eligible universe equities instead of a single asset. Its `initial_capital` becomes a **shared cash pool** that is the bot's hard budget: a buy executes only if it fits in remaining cash, so total deployed capital can never exceed the budget no matter how many symbols signal. Exits liquidate fully and return cash to the pool for reuse within the same tick (deterministic order); leftover cash stays idle.
- The single inline position on a session is replaced by a **collection of open positions** (at most one long position per symbol; no pyramiding).
- **ATR (Average True Range) risk-based position sizing** within the pool: each name targets an equal dollar risk (`risk$ = budget × risk_pct`; `shares = floor(risk$ / (k × ATR))`), then capped by a maximum per-name fraction of the budget and by remaining cash. ATR is computed deterministically from the bot's signal-bar history each tick.
- A configurable **maximum-concurrent-positions** cap bounds how many names the bot holds at once; when more symbols signal than slots remain, a deterministic rule decides which win.
- The whole-bot **drawdown kill-switch** and **per-position take-profit / stop-loss** are retained, now applied across the basket.
- Daily **value snapshots, KPIs, and the dashboard performance adapter** are generalized to a multi-position bot (value = cash + sum of marked-to-market positions).
- Frontend: the bot build form replaces free-text ticker entry with a **universe-backed searchable picker** supporting multi-select of individual eligible stocks plus a **"whole universe"** option (no new assets may be added). The bot detail page shows **multiple open positions**, and **creating a bot navigates to its detail page**.
- A new **dedicated strategy explanation page** (reachable from the Bots area) explains what the MA-Crossover strategy does, with an illustrative crossover chart, and documents the risk controls (ATR sizing, per-name cap, max positions, shared budget ceiling, take-profit, stop-loss, drawdown kill-switch).

## Capabilities

### New Capabilities
<!-- none — the strategy explanation page is navigation/view behavior under app-shell -->

### Modified Capabilities
- `strategy-bots`: session lifecycle now binds a set of equities to one shared, hard-capped capital pool instead of a single asset; position sizing becomes ATR risk-based with a per-name cap, a shared-budget ceiling, and a max-concurrent-positions limit; the single inline position becomes a collection of positions; snapshots, KPIs, and the dashboard performance adapter generalize to a multi-position bot. Take-profit/stop-loss and the drawdown kill-switch are preserved. Adds strategy-metadata (an explanation/description) to the strategy registry.
- `app-shell`: the Bots build form gains a universe-backed searchable, multi-select ticker picker plus a whole-universe option (no new assets); a new dedicated strategy explanation page with an illustrative chart and risk-control documentation, plus its navigation entry; the bot detail page renders multiple open positions; creating a bot navigates to its detail page.

## Impact

- **Backend** (`backend/src/cadence/strategy_bots/`): `models.py` (session loses single `asset_id`/inline position columns; gains a positions relationship and the budget/sizing/max-positions config), `service.py` (multi-asset create/validation; shared-pool tick execution; ATR sizing; snapshots/KPIs; dashboard adapter), `constants.py` (strategy metadata + sizing defaults), `ma_crossover.py`/strategy registry (explanation field), plus an Alembic migration for the schema change.
- **API** (`/api/v1/bots`, shared `api/schemas.py`): create accepts a symbol set / whole-universe flag + sizing params; session and KPI responses expose multiple positions; strategy catalog exposes the explanation.
- **Frontend** (`frontend/src/pages/bots/`, `frontend/src/api/bots.ts`, `frontend/src/api/assets.ts`, `types/api.ts`, nav/router): new universe-backed multi-select ticker picker component, whole-universe option, multi-position detail view, create→detail navigation, new strategy explanation page + route + nav entry.
- **Specs**: delta specs for `strategy-bots` and `app-shell`.
- **Migration note**: the single-asset → multi-asset model is a breaking schema change; design.md resolves how existing single-asset bots are reconciled (N=1 case vs. coexistence/backfill).
