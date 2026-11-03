## Context

See proposal.md — Why. The strategy-bots subsystem exists and is live: a `BotSession`
is bound to one `asset_id` + frozen `ticker` with inline single-position columns
(`position_qty`/`position_avg_price`/`position_opened_at`), does long-only all-in
whole-share sizing on an MA-Crossover signal, runs an IEX-feed 5-minute intraday tick
(market-hours gated, stateless recompute, skip-on-stale-data), has optional
take-profit/stop-loss + a drawdown kill-switch, daily value snapshots + KPIs, and a
dashboard performance adapter (`kind='bot'`). Spec: `openspec/specs/strategy-bots/spec.md`.

Constraints that shape the approach: schema is owned by Alembic; service.py holds all
business logic and DB access; the tick must stay deterministic and stateless (only
positions, ledger, and snapshots persist — no in-memory carry between ticks); market
data comes from the subsystem's configured provider behind a Protocol; the broker is
behind a Protocol with an injectable stub for tests. This is a paper-trading app on
Alpaca paper; there is no real-money exposure.

## Goals / Non-Goals

**Goals:**
- One `BotSession` trades a *set* of eligible universe equities from a single shared
  cash pool that is a hard budget ceiling.
- Position sizing is risk-aware (ATR), bounded by a per-name cap, a max-concurrent
  limit, and remaining cash — never exceeding the budget.
- The tick stays deterministic, stateless, and per-symbol freshness-gated.
- Snapshots, KPIs, and the dashboard adapter work unchanged *in shape* for a
  multi-position bot.
- A universe-backed picker and a strategy explanation page make the model legible.

**Non-Goals:**
- No new indicators or strategies — MA-Crossover remains the only strategy; ATR here
  is a *sizing* input, not a tradable signal (it does not create entries/exits).
- No short-selling, no pyramiding/scaling into an existing position, no options.
- No intra-name rebalancing / trimming toward target weights (buys are all-at-once up
  to the sized quantity; sells are all-out). See Decisions.
- No per-position benchmark; the bot keeps a single benchmark.
- No backtesting, no price-history ingestion (out of project scope).

## Decisions

### D1 — Session trades a symbol set; `initial_capital` is a shared cash pool
The session drops `asset_id`/`ticker` and gains a **tradable symbol set** plus a
persisted **cash** balance. `initial_capital` = the budget = the starting cash. A buy
executes only if its cost fits in *remaining* cash after the configured cash buffer, so
`Σ open position cost ≤ budget` always holds. Exits return proceeds to cash, reusable by
later entries within the same tick. Alternative rejected: independent per-symbol sleeves
— that is behaviourally identical to N separate single-asset bots (the user's explicit
objection) and makes capital non-fungible.

### D2 — Positions become a collection (`bot_positions`)
Replace the three inline position columns with a `bot_positions` child table: one row per
*open* long position, unique on (session, asset), carrying qty / avg entry price /
opened-at. At most one open row per symbol (no pyramiding). Closed positions are already
captured by the existing `bot_trades` ledger; a position row is deleted on full exit.
Session value = `cash + Σ(qty × mark price)`.

### D3 — ATR risk-based sizing, with a `sizing_method` enum preserving legacy all-in
Add `sizing_method ∈ {atr_risk, all_in}`. New multi-asset bots default to **atr_risk**:
- `risk_dollars = budget × risk_pct`
- `per_share_risk = atr_k × ATR(atr_period)` on the symbol's signal-bar history
- `target = floor(risk_dollars / per_share_risk)`
- cap by per-name notional: `target = min(target, floor((budget × max_position_pct) / price))`
- cap by cash: `target = min(target, floor(available_cash / price))`
- skip if `target < 1` share.

`all_in` reproduces today's behaviour (`floor(available_cash / price)` within the cap)
and is what migrated single-asset bots use, so existing bots keep their behaviour. ATR is
computed deterministically from the already-fetched bars (Wilder's True Range mean); if
`ATR ≤ 0` or history is insufficient the symbol is skipped for sizing that tick (treated
like stale data). Defaults (all configurable per bot): `atr_period=14`, `atr_k=2.0`,
`risk_pct=0.01` (1%), `max_position_pct=0.25`, `max_positions=10`, existing
`cash_buffer_pct` retained. Alternative rejected: GARCH vol targeting — heavier
dependency, no better fit for a 5-minute deterministic tick.

### D4 — Deterministic, stateless tick ordering
Per tick (market open only): (1) refresh marks; (2) **exits first** — for every open
position evaluate drawdown kill-switch (whole bot), then per-position take-profit/
stop-loss, then the strategy EXIT signal; sell fully, return cash. (3) **entries next** —
iterate candidate symbols with an ENTER_LONG signal in a deterministic order (ascending
ticker), and for each, if open-position count `< max_positions` and sizing yields ≥1
share affordable from remaining cash, buy. Stop when `max_positions` reached or cash
exhausted. This makes the max-positions tie-break deterministic (ascending ticker wins)
and keeps the runner stateless (ATR/SMA recomputed each tick). Per-symbol freshness gate
unchanged: a stale/missing fresh bar skips that symbol for the tick.

### D5 — "Whole universe" snapshots the eligible set at creation (v1)
Selecting "whole universe" resolves the current eligible universe equities and stores
them as the session's explicit symbol set (same storage as hand-picked symbols). The set
is **fixed** for the session's life. Rationale: a fixed set keeps the benchmark,
contributions, KPIs, and tick fully deterministic and avoids a bot silently starting to
trade newly-added names. Alternative (dynamic re-resolution each tick) is recorded as a
future option (see Open Questions) but not built now. The backend still validates every
symbol is an eligible universe stock; no new assets can be introduced.

### D6 — Snapshots / KPIs / dashboard adapter generalize, shape unchanged
Daily snapshot stores `total_value = cash + Σ marked positions`, plus realised/unrealised
P&L aggregated across positions. KPIs compute from the session's own ledger + snapshots
(unchanged contract, now summing across positions). The dashboard adapter keeps the same
per-session performance shape (`kind='bot'`, value series, contributions, since-inception
benchmark on the same contribution-aware buy-and-hold basis as AI sessions) — only the
value computation changes from one position to a sum.

### D7 — Strategy explanation = backend metadata + client-rendered page
The strategy registry/catalog gains an **explanation** field (what the strategy does) so
the catalog endpoint returns it per strategy. The dedicated page renders that text plus a
client-side **illustrative** crossover chart (deterministic synthetic fast/slow SMA series
with entry/exit markers — not live data) and static documentation of the subsystem risk
controls (ATR sizing, per-name cap, max positions, shared budget ceiling, take-profit,
stop-loss, drawdown kill-switch), which are subsystem-level, not per-strategy. Rationale:
strategy mechanic belongs to the registry (extensible as strategies are added); risk-
control docs and the illustrative chart are presentation and stay in the client.

### D8 — Universe-backed multi-select picker (new shared component)
A new frontend combobox queries `listAssets({ search, membership:'universe',
category:'stock' })` for typeahead, supports selecting multiple eligible stocks, and
offers a "whole universe" action. No free-text symbol can be submitted — only chosen
universe assets — so the UI matches the backend's existing membership validation. The bot
detail page renders the multiple open positions; creating a bot navigates to its detail
page.

## Risks / Trade-offs

- **Breaking schema change** → Migrate existing single-asset sessions to the N=1 shape
  (one symbol, one position row if currently open, `sizing_method=all_in`,
  `max_positions=1`, caps backfilled to preserve behaviour). Down-migration is lossy for
  any true multi-symbol bot (can't collapse to one `asset_id`); documented and acceptable
  pre-release.
- **Whole-universe bot spreads thin / many tiny orders** → `max_positions` + per-name cap
  + the ≥1-share/min-notional skip bound concurrency and dust; snapshot set keeps it
  stable.
- **ATR sizing on sparse IEX intraday bars could misprice risk** → insufficient/zero ATR
  skips sizing for that symbol that tick (no trade on bad data), consistent with the
  existing freshness skip.
- **More market-data calls per tick (one fetch per symbol)** → acceptable at the 5-minute
  cadence; reuse the existing per-symbol fetch + skip-on-stale path; a universe bot's cost
  scales with `max_positions`-bounded activity, not set size, for execution.
- **Larger blast radius** (models, service, snapshots, KPIs, adapter, API, FE) → keep the
  tick's sizing and budget-ceiling logic in small pure, unit-tested helpers (ATR,
  size_position, enforce-budget) so correctness is testable in isolation.

## Migration Plan

1. Alembic migration: create `bot_positions` (+ the symbol-set storage); add
   `cash`, `sizing_method`, `risk_pct`, `atr_period`, `atr_k`, `max_position_pct`,
   `max_positions` to `bot_sessions`; drop `asset_id`, `ticker`, and the inline position
   columns.
2. Data backfill in the migration: for each existing session, insert its single symbol
   into the symbol set; if it has an open position, insert one `bot_positions` row; set
   `cash = initial_capital − open cost` (or `= current cash` if tracked); set
   `sizing_method='all_in'`, `max_positions=1`, `max_position_pct=1.0`, risk/ATR defaults.
3. Deploy backend + frontend together (API shape changes).
4. Rollback: down-migration restores the dropped columns from the single symbol/position
   (lossy for multi-symbol bots — they cannot be represented single-asset; documented).

## Open Questions

- **Dynamic whole-universe tracking** (re-resolve the eligible set each tick so a bot
  "follows" the universe) — deferred; D5 ships the snapshot set. Revisit if desired; it
  would not change the sizing/budget specs, only the set-resolution requirement.
- **Exact default for `max_position_pct`/`risk_pct`** may be tuned during apply from a
  quick sanity check against typical universe prices; defaults above are the starting
  point and do not change the spec's required behaviour.
