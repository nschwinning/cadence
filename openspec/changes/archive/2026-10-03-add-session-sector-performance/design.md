## Context

See `proposal.md` (Why) for motivation. Current state that shapes the approach:

- A paper-trading session's performance is already computable:
  `paper_trading/service.py compute_session_value()` marks open positions to market and
  returns, per position, `ticker`, `quantity`, `price`, `market_value`,
  `unrealised_pnl`, and `return_pct` (so a position's cost basis is derivable as
  `market_value − unrealised_pnl`). Realised P&L lives on `ClosedPosition`
  (`realized_pnl`, `return_pct`, `quantity`), retrievable via `get_closed_positions()` /
  `list_closed_position_pnls()`. Open positions are `SessionPosition`
  (`(session_id, ticker)` unique).
- Sector/category data lives only on the asset catalogue: `Asset.category`
  (`SQLEnum(AssetCategory)`, non-null — effectively stock|crypto for held assets) and
  `Asset.sector` (`SQLEnum(Sector)`, **nullable** — crypto and most funds have none).
  The join key is `Asset.ticker`, stored upper-cased via `normalize_ticker`.
- **The paper-trading module never joins to `Asset` today** — there is no existing read
  that returns a position with its sector or category, and no sector/category
  aggregation anywhere except the asset-universe composition donuts
  (`dashboard/service.py _breakdown()` → `BreakdownEntry {key, count}`, rendered by the
  data-shape-agnostic SVG donut `components/dashboard/BreakdownTile.tsx`). Those donuts
  show **counts**, not signed values.
- `dashboard/service.py` already uses a null-sector bucket convention
  (`NO_SECTOR_KEY`).

## Goals / Non-Goals

**Goals:**
- Attribute a session's realised + unrealised P&L to sectors and categories, with market
  value and a return % per group, via a new ticker→`Asset` join.
- Surface it on the session detail page with a sign-aware presentation.

**Non-Goals:**
- No dashboard-level or cross-session aggregation (session detail page only).
- No composition donut (user chose performance attribution, not composition); donuts
  cannot show negative slices anyway.
- No new storage or migration — the breakdown is derived on read.
- No change to KPIs, the value chart, or any other existing read.

## Decisions

### D1 — Performance = total P&L = realised + unrealised
Each group's performance is its closed-position realised P&L plus its open-position
unrealised P&L, with the group return = group total P&L ÷ group invested cost basis.
*Alternatives:* unrealised-only (ignores booked gains/losses — misleading for a session
that has rotated positions) or realised-only (ignores current exposure). Rejected;
total P&L is the complete attribution and matches how the KPI tiles already frame
performance.

### D2 — Derive on read, no storage, no migration
Compute the breakdown at request time by reusing `compute_session_value()` for
mark-to-market, `get_closed_positions()` for realised P&L, and a single catalogue query
for the sector/category of every ticker involved. *Alternative:* persist per-snapshot
sector aggregates — rejected as premature; the read is cheap (one extra `Asset` query)
and always current, and it works retroactively for existing sessions with no backfill.

### D3 — Ticker→Asset join with explicit buckets for the two gaps
Collect the distinct tickers across open and closed positions, normalise them to the
catalogue casing (`normalize_ticker`), and fetch `Asset.ticker, Asset.category,
Asset.sector` for them in one query. Two edge cases get explicit buckets so no P&L is
ever dropped or the request ever fails:
- **Null sector** (`Asset.sector is None`, e.g. crypto/funds) → a "No sector" bucket in
  the by-sector breakdown only; the asset's category is still used normally in the
  by-category breakdown.
- **Unmatched ticker** (position ticker not in the catalogue — a deleted/renamed asset)
  → an "Unknown" bucket in *both* breakdowns.
This mirrors the existing `NO_SECTOR_KEY` convention and keeps the aggregation total
equal to the session's overall realised + unrealised P&L.

### D4 — Return guards divide-by-zero → unavailable
A group's return is `total_pnl / cost_basis`; when the group's invested cost basis is
zero (e.g. a group that is entirely closed at zero basis, or an unusual data state) the
return is reported as `null`/unavailable rather than raised or shown as a bogus number.
The frontend renders a "not available" state for such groups, reusing the KPI
"unavailable" pattern.

### D5 — Signed presentation, not a donut (frontend)
Group P&L can be negative, which the existing `BreakdownTile` donut cannot represent.
The new card uses a sign-aware row / diverging-bar layout: per group, the total P&L as a
money amount coloured by sign (gain/loss, matching the KPI tiles), the return %, and a
bar sized by magnitude. A sector/category toggle switches the grouping. *Alternative:*
reuse the donut for composition — rejected; it answers a different question
(composition, not performance) and can't show losses.

### D6 — New endpoint and schema, additive only
Add `GET /paper-trading/sessions/{id}/sector-performance` returning
`{ by_sector: SessionGroupPerformance[], by_category: SessionGroupPerformance[] }`
where `SessionGroupPerformance = { key, market_value, realized_pnl, unrealized_pnl,
total_pnl, return_pct: float | null }`. Unknown session → 404, matching the existing
session reads. No existing schema or endpoint changes.

## Risks / Trade-offs

- **[Ticker casing mismatch between positions and the catalogue]** → D3 normalises every
  position ticker with `normalize_ticker` before the join; a covering test asserts the
  join matches regardless of stored casing.
- **[P&L silently dropped for deleted/renamed assets]** → D3's "Unknown" bucket; a test
  asserts an unmatched ticker lands there and the group totals still sum to the session
  total.
- **[Return divide-by-zero]** → D4; a test covers the zero-cost-basis group.
- **[Extra read cost per session view]** → one additional indexed `Asset` query over the
  session's distinct tickers; negligible, and only on the detail view.

## Migration Plan

None. Pure read/join; no schema change, no Alembic migration, no backfill. The feature
works for all existing sessions immediately. Rollback is removing the endpoint and the
frontend card; nothing persisted.

## Open Questions

None that affect the specs, approach, or task breakdown.
