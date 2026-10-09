## Context

The fee model lives behind one choke point — `paper_trading.service.record_trade`
— plus two estimators that mirror it: the executor's `_reserve_cash_buffer`
(sizes a protective cash buffer) and the dashboard's `_range_fees` (projects
range-scoped fees). All three read `settings.TRANSACTION_COST_USD` (flat `1.0`) and
assume one flat cost per trade. `record_trade` is called from four sites
(`paper_trading.service` scope-change close; `ai_portfolio.service` build,
rebalance, stop-loss), and every one of them has the asset class in scope (`cls`
or an `_asset_class_map`). `AssetClass` has exactly two members in this system —
`EQUITY` and `CRYPTO` (Alpaca). `total_fees` is a non-nullable session column;
individual `PaperTrade` rows store `ticker`, `quantity`, `price`, `notional`
(`quantity*price`) and `filled_price`, but **no per-trade fee**.

## Goals / Non-Goals

**Goals:**
- Charge $0 on equity trades and `CRYPTO_FEE_PCT × executed_notional` on crypto
  trades, at the single `record_trade` choke point.
- Keep the executor cash buffer and the dashboard fee estimate consistent with the
  new model.
- Replace the now-uninformative daily-average-transaction-cost KPI/tile with a
  daily-average-orders KPI/tile, and record each day's filled-order count in the
  daily-run learning snapshot.
- Restate historical fees one-time so existing sessions reflect the new model:
  recompute each session's `total_fees` from its trade ledger and re-derive the
  affected value snapshots. Data-only; no DB-schema change (`total_fees`, the
  value-snapshot columns, and the learning snapshot's JSONB `document` keep their
  shape). The only interface changes are one KPI field rename (read API + TS type)
  and one UI tile swap.

**Non-Goals:**
- Modeling equity slippage as an explicit fee (already in fill prices) or SEC/FINRA
  sell fees (sub-cent, negligible).
- Maker/taker tiering or Alpaca volume tiers — a single flat crypto percentage.
- Re-versioning the rebalance prompt (see Decisions → prompt).
- Storing a per-trade fee amount (would require a *schema* migration — out of scope;
  the backfill is data-only).
- Re-quoting prices or re-running valuation against the broker during the backfill
  (the restatement adjusts stored values by the fee delta only).

## Decisions

### 1. Compute the fee at `record_trade`, asset class passed by the caller

`record_trade` gains a required-by-callers `asset_class: AssetClass` parameter
(keyword-only, consistent with the existing signature). The fee is:

```
notional = quantity * (filled_price if filled_price is not None else price)
fee = settings.CRYPTO_FEE_PCT * notional if asset_class is CRYPTO else 0.0
row.total_fees += fee
```

Using the **executed** notional (filled price when present) matches what the
position actually cost. The four call sites thread the class they already hold:
the executor loops in `_apply_build_trades`/`_apply_rebalance_trades` look it up
from the in-scope `asset_classes` map (threaded in as a parameter — `TradeResult`
has no class field, and adding one would touch many construction sites), and the
stop-loss / scope-change paths pass their local `cls`.

*Alternative considered:* look the asset up by ticker inside `record_trade`. Rejected
— it couples the recorder to the asset table, adds a query per trade, and the class
is already in hand at every caller.

### 2. Retire `TRANSACTION_COST_USD`, add `CRYPTO_FEE_PCT`

`CRYPTO_FEE_PCT: float = 0.0025` (0.25%, Alpaca base-tier taker). `TRANSACTION_COST_USD`
is removed rather than kept at `0.0`: leaving a dead flat-fee knob invites the old
mental model back, and every reader is being updated anyway. The simplest coherent
model is "equities free, crypto a percentage," with one setting for the one
non-zero case.

### 3. Executor cash-buffer fee estimate

`_reserve_cash_buffer` keeps the "greater of percentage vs fee estimate" shape. The
fee-estimate term becomes the asset-class-aware estimate: `0` when the run has no
crypto candidate, else a conservative upper bound `CRYPTO_FEE_PCT × base` (crypto
notional for the run can never exceed the sizing base). The caller passes whether
the run includes any crypto candidate (replacing the raw `candidate_count`, which
no longer maps to a flat cost). Because `REBALANCE_CASH_BUFFER_PCT` (1.5% default)
dwarfs `CRYPTO_FEE_PCT` (0.25%), the percentage term dominates in every default
config — the fee term only matters if an operator zeroes the percentage, where the
conservative bound still keeps cash non-negative. This keeps the buffer correct
without threading per-ticker crypto notionals into the pre-weight reserve step.

*Alternative considered:* compute the exact crypto-scoped notional at reserve time.
Rejected — weights aren't resolved yet when the build reserve is applied, and the
conservative bound is both safe and dominated by the percentage term anyway.

### 4. Dashboard `_range_fees` without a per-trade fee column

With no stored per-trade fee and no migration, the range estimate is recomputed
from trade rows: sum `CRYPTO_FEE_PCT × notional` over the range's trades whose
ticker belongs to a **crypto-category** asset (joined/filtered via the `Asset`
table), equity trades contributing zero. This mirrors the charge model closely
(it uses the stored `notional = quantity*price`; the tiny filled-vs-quoted
difference is acceptable for a projection). The "Max" range already reconciles
against session-level `total_fees` elsewhere; this function only scopes a
sub-range.

### 6. Swap the daily-average-cost KPI for daily-average-orders

Once equities are free, `daily_avg_transaction_cost` (cumulative fees ÷ snapshot
days) reads ~0 for equity-only sessions and is no longer a useful headline. It is
**replaced**, not supplemented, by `daily_avg_orders`:

```
daily_avg_orders = count_session_trades(session, session_id) / len(snapshots)
                   if snapshots else None  # None until the first snapshot
```

The numerator reuses the existing `count_session_trades` helper (a `COUNT(*)` over
the session's `PaperTrade` rows — "orders" = recorded trades); the denominator is
the same recorded-daily-value-snapshot count the old KPI used, so the metric is a
true "orders per snapshot day" average and keeps the identical `None`-without-snapshots
guard. The field is renamed everywhere it travels: `SessionKpis`,
`PaperTradingSessionKpisRead`, the explicit router mapping in
`api/routers/paper_trading.py`, and the TS `PaperTradingSessionKpis` type. The
session-detail tile takes the same grid slot (ten tiles, two rows preserved) but
renders a **number** (e.g. two decimals) rather than a currency amount, and the
adjacent transaction-fees tile's stale `$1 per executed trade` hint is corrected.

*Spec mechanics:* because an OpenSpec MODIFIED block cannot drop a scenario and a
requirement cannot be removed and re-added under the same name, the two capabilities
that carried the cost KPI/tile are **removed and re-added under a new name**
(`Live session performance KPIs` → `Live session performance KPI summary`;
`Session performance KPI tiles` → `Session performance KPI tile grid`), mirroring the
`move-breakdown-donuts-to-assets` precedent. This is a spec-authoring detail only; no
code reads requirement titles.

*Alternative considered:* keep `daily_avg_transaction_cost` in the read model and
only swap the tile. Rejected — it leaves a vestigial, unsurfaced field and the user
asked to exchange the metric, not add one.

### 7. Record the day's order count in the daily-run learning snapshot

The backend-only daily-run learning `document` already embeds the day's reconciled
`orders` list and the run's `run_stats`. To make the per-day trading activity (the
basis of the new KPI) first-class for offline learning, `_build_run_document` adds
`orders_count = len(trades)` alongside `orders`. It is a derived count over
already-consolidated data, lives in the existing JSONB `document`, and needs no
migration. A no-run day's count is `0`. The snapshot stays backend-only (no read
schema / API / frontend surface).

### 8. One-time historical backfill (full restatement, data-only migration)

The retired flat $1/trade fee is already baked into every existing session's
`total_fees` and into the historical value snapshots (which subtract `total_fees`
from portfolio value). Leaving that history under the old model would make past
valuations inconsistent with the new one — equity-heavy sessions would read as
permanently poorer by $1 per past trade. So the change ships a **one-time data
migration** that restates history as if the asset-class-aware model had always
applied. It changes recorded values only; **no table or column is added or
removed**.

**Per-trade fee under the new model.** For each `PaperTrade` row:

```
new_fee = CRYPTO_FEE_PCT_LITERAL * quantity * (filled_price if filled_price is not None else price)   # crypto
        = 0.0                                                                                          # equity
correction = HISTORICAL_FLAT_FEE_LITERAL - new_fee      # = 1.0 - new_fee; the fee removed from this trade
```

A trade's asset class is resolved by **joining its ticker to the `Asset` table**
(`category == CRYPTO` → crypto, else equity); a ticker that no longer resolves
falls back to equity (no fee). The migration is **self-contained**: it hardcodes
the crypto percentage (`0.0025`) and the historical flat fee (`1.0`) as literals
rather than reading runtime `settings`, so a later settings change can't retro-alter
what the migration did.

**`total_fees`.** Each session's total is **set** to `Σ new_fee` over its trades
(not decremented — recompute from the ledger so the result is idempotent).

**Value snapshots.** Removing fees lifts portfolio value additively. Because
`total_value = allocated_capital + realised_pnl − total_fees + unrealised` and a
snapshot stored the value *as of its date*, the correct lift for a snapshot dated
`D` is the cumulative fee removed for all trades executed on or before `D`:

```
cumCorr(D) = Σ correction(t) for trades t with executed_at.date() ≤ D
new_total_value(D) = stored_total_value(D) + cumCorr(D)
new_cash_value(D)  = stored_cash_value(D)  + cumCorr(D)   # positions_value unchanged
```

Walk each session's snapshots in date order, accumulating `cumCorr` over the trades
in each `(prevSnapDate, thisDate]` window. Daily P&L is a difference of total
values, so it is recomputed from the corrected series exactly as
`record_value_snapshot` does:

```
baseline       = prior_snapshot.new_total_value            (or allocated_capital − Σ contributions for the first)
contributed(D) = Σ capital-event amounts in (prevSnapDate, D]   (first snapshot: Σ amounts ≤ D)
new_daily_pnl(D)     = new_total_value(D) − contributed(D) − baseline
new_daily_pnl_pct(D) = new_daily_pnl(D) / baseline   if baseline > 0 else 0.0
```

This is exact and needs **no broker re-quoting**: `positions_value` is reused
as-stored, and the only thing that moved is the additive fee term. Capital events
(contributions) are already in the ledger and are read the same way
`record_value_snapshot` reads them.

*Alternative considered:* going-forward only (leave history at $1). Rejected by the
user — they want past valuations to reflect the realistic model. *Alternative:*
keep historical crypto fees at the flat $1 and only zero equities. Rejected — the
user chose full re-pricing of crypto history to `0.25% × notional`.

### 5. Rebalance prompt left unchanged (explicit)

The existing "Rebalancing prompt informs the agent of transaction costs"
requirement and its frozen prompt version are **not** modified here. Telling the
agent that trading has a cost remains a useful anti-churn nudge and is still
literally true for crypto; re-versioning the prompt (freeze semantics, a new DB
prompt row) is a separate concern and out of scope for a pure cost-model fix.
Flagged so this is a conscious choice, not an oversight.

## Risks / Trade-offs

- **Test churn:** many existing tests assume the flat `$1` fee (valuation, KPIs,
  cash-buffer exact-quantity asserts, dashboard range fees). They must be updated
  to the new expected amounts; several executor/service suites already pin the
  buffer/cost to zero for exact-quantity asserts and will keep doing so (now via
  `CRYPTO_FEE_PCT = 0` + `REBALANCE_CASH_BUFFER_PCT = 0`).
- **Removing a setting:** anything referencing `TRANSACTION_COST_USD` (including
  `.env`/deploy config and tests) must be updated in lockstep; a stray reference
  becomes an `AttributeError`. A repo-wide grep gates completion.
- **Dashboard join cost:** `_range_fees` now joins trades to assets to find crypto;
  negligible at current scale, and scoped to one session's trades in a range.
- **Estimate vs charge drift:** the dashboard uses quoted `notional` while the
  charge uses filled notional — a projection-only discrepancy, not a ledger error.
- **Backfill correctness:** the snapshot re-derivation assumes the stored
  `positions_value` and capital-event ledger are the source of truth and that the
  only historical error was the fee term. If a past snapshot was written with a
  different valuation formula, the additive lift could drift; current history was
  all written by the same `record_value_snapshot`, so this holds. The migration is
  idempotent (recomputes from the ledger), so a re-run is safe.
- **Migration self-containment:** the migration hardcodes the crypto percentage and
  historical flat fee as literals rather than importing runtime `settings`/ORM
  models, so later config or model changes can't alter what a past migration did —
  the standard Alembic data-migration discipline.
