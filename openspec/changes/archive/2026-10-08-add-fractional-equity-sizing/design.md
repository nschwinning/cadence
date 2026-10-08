## Context

See proposal.md — Why. Key current-state facts that shape the approach:

- The AI returns only `allocation_pct` target weights; the executor computes every
  quantity as `base_capital * weight / price` using its own broker quote. So this is
  purely an executor sizing change — no agent/schema change.
- Crypto already sizes fractionally via `round(qty, CRYPTO_QTY_PRECISION=8)` and a
  dollar dust skip (`MIN_CRYPTO_NOTIONAL_USD`). Equities truncate with
  `float(int(capital / price))` and a `< 1 share` skip at build (`_open_long`),
  rebalance (`_plan_equity`, `int(pos.quantity)` / `int(base*weight/price)` with
  `|delta| < 1` no-op guards), and exit.
- Everything below the executor is already float-capable: `Order.quantity: float`,
  `PaperTrade.quantity`/`notional` are `Float` columns, Alpaca `submit_order` sends
  `str(order.quantity)`, StubBroker fills floats.
- `BrokerAsset.fractionable` is already parsed from Alpaca `/v2/assets` and returned by
  `broker.get_asset(...)`, but nothing consults it.
- `assets.alpaca_symbol` and the add-time `broker.get_asset(...)` tradability check
  already exist, so add-time is already the natural place to capture fractionability.

## Goals / Non-Goals

**Goals:**
- Size fractionable equities to their exact target weight; stop stranding the
  sub-one-share remainder as idle cash.
- Keep non-fractionable (and unknown) equities on today's exact whole-share behavior —
  zero behavior change for them.
- Source fractionability cheaply at sizing time (no per-ticker API calls during a
  rebalance).

**Non-Goals:**
- No AI output/schema change; weights still drive sizing.
- No `notional` (dollar) ordering — we keep `qty`-based orders.
- No change to crypto sizing beyond the cosmetic requirement-text split.
- No change to the cash-buffer, guardrail, sells-before-buys, or redeploy logic other
  than letting them operate on fractional equity quantities.

## Decisions

### 1. Persist `fractionable` on the asset row (chosen) vs. live lookup at sizing time
Add a nullable `fractionable: Mapped[bool | None]` column to `assets`. Populate it in
`add_asset` from the `BrokerAsset` already fetched for the tradability check (no extra
call). The Alembic migration is **schema-only** (add the nullable column); backfill is a
separate `assets/service.py` helper (`backfill_fractionable(session, broker)`) that
iterates rows with `fractionable IS NULL`, calls `broker.get_asset` once each, and sets
the flag — fail-open to `NULL` per asset. Keeping network I/O out of the migration
follows the project convention that services own external I/O and Alembic owns schema.

Rationale: the executor reads the flag straight off the in-scope asset rows it already
loads — no N extra API calls per rebalance, no new failure mode on the hot path. The
live-lookup alternative avoids a migration but adds per-run Alpaca calls and a
fail-open path inside sizing; rejected for the hot-path cost. `NULL` (unknown) is
treated as non-fractionable, so the feature is strictly opt-in per asset and safe on a
partially-backfilled table.

### 2. Gating predicate: `fractionable is True`
The executor sizes fractionally only when the asset's stored flag is exactly `True`.
`False` and `None` both mean whole shares. This makes "unknown" behave identically to
today, so a backfill failure or a brand-new row degrades safely rather than placing a
fractional order Alpaca would reject.

### 3. New constants mirroring crypto
- `EQUITY_QTY_PRECISION = 6` — decimal places for fractional equity quantities (Alpaca
  supports up to 9; 6 is ample and avoids float-noise dust).
- `MIN_EQUITY_NOTIONAL_USD` — dollar dust threshold replacing the `< 1 share` skip for
  fractionable equities. Whole-share (non-fractionable) sizing keeps its existing skip
  semantics (can't buy a fraction, so `< 1 share` still means skip).

Sizing becomes, per equity:
- fractionable: `qty = round(capital / price, EQUITY_QTY_PRECISION)`, skip if
  `qty * price < MIN_EQUITY_NOTIONAL_USD`.
- non-fractionable: `qty = float(int(capital / price))`, skip if `qty < 1` (unchanged).

Rebalance `_plan_equity`: for fractionable assets, compute `current`/`target` as floats
(`round(base*weight/price, EQUITY_QTY_PRECISION)`), `delta = round(target - current, ...)`,
and gate on `abs(delta) * price >= MIN_EQUITY_NOTIONAL_USD` (mirroring `_plan_crypto`);
for non-fractionable assets keep the integer-share delta with `|delta| >= 1` guards.
Exit path: fractionable sells the full fractional `pos.quantity`; non-fractionable keeps
`float(int(abs(pos.quantity)))`.

### 4. Order type / TIF for fractional equity orders
Alpaca accepts fractional equity orders only as market or day-limit orders with
`time_in_force=day`. Task 1 audits what `submit_order`/`buy`/`sell` currently send for
equities; if the current equity order is already a market/day order, no change is
needed beyond a test asserting it. If not, the executor/broker is adjusted so fractional
equity orders meet the constraint. Whole-share equity orders are left exactly as they
are.

## Risks / Trade-offs

- **Partially-backfilled table after deploy** → gating on `fractionable is True` means
  un-backfilled rows size whole-share (today's behavior) until the migration backfill
  runs; no incorrect fractional orders. Backfill is idempotent and fail-open.
- **Backfill hits Alpaca rate limits / is offline at migration time** → backfill is
  best-effort per asset, leaves `NULL` on failure, and can be re-run (re-adding or a
  follow-up pass sets it). Migration must not fail the deploy if Alpaca is unreachable —
  it catches per-asset errors and leaves `NULL`.
- **Float dust / rounding** → `EQUITY_QTY_PRECISION` plus the `MIN_EQUITY_NOTIONAL_USD`
  guard keep tiny residual quantities from generating no-op or rejected orders, same as
  crypto today.
- **Alpaca rejects a fractional order we thought was fractionable** → the stored flag
  comes straight from Alpaca's own `/v2/assets`, so divergence is unlikely; a rejected
  order already surfaces through the existing order-status reconciliation path rather
  than corrupting the ledger.

## Migration Plan

1. Add nullable `fractionable` column (schema-only Alembic revision, `down_revision` =
   current head).
2. Deploy executor + `add_asset` changes together with the migration. New adds populate
   `fractionable` immediately; existing rows stay `NULL` (= whole-share) until backfilled.
3. Run the `backfill_fractionable(session, broker)` helper once post-deploy (operator
   invokes it; e.g. a short `uv run python -m ...` one-off). It is idempotent and
   fail-open, so it can be re-run to fill rows left `NULL` by a transient Alpaca error.
4. Rollback: `downgrade` drops the column; roll back code and schema as a pair (the
   executor reads the column, so reverting one without the other is unsupported).
