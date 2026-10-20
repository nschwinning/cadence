## Context

The daily P&L Pushover push is assembled per session in
`ai_portfolio/snapshots.py::snapshot_all_sessions`: inside the per-session loop
it records the day's `SessionValueSnapshot`, computes KPIs, builds a `holdings`
list, and calls `ai_portfolio/notifications.py::_session_snapshot_message`. The
message's best/worst line comes from `_best_worst_line(holdings)` (max=Best,
min=Worst, `_signed_pct` ×100 formatting).

Today `holdings` is built as `(ticker, pos["return_pct"])` from
`snapshot.positions`, and `return_pct` is a **since-entry** return —
`paper_trading/service.py` computes it as `(price / avg_cost) − 1`. Two sessions
holding the same ticker at different average cost therefore show different (even
opposite-sign) "performer" percentages on the same day, while the message header
(`daily_pnl_pct`) is a genuine daily figure. The fix makes the performer line a
true day-over-day price change.

## Goals / Non-Goals

**Goals**
- Best/worst performer line reports each holding's daily price change
  (`current snapshot price ÷ previous snapshot price − 1`), so the same ticker
  reads identically across all sessions' pushes on a given day.
- Deterministic, unit-testable, with explicit edge-case handling.

**Non-Goals**
- No change to `return_pct` in the snapshot document (other consumers keep it).
- No change to the header P&L math, snapshot scheduling, weekend crypto gating,
  benchmark comparison, or the daily-run learning snapshot.
- No migration, no schema change, no API change, no frontend change.

## Decisions

### D1 — Compute the daily change from consecutive snapshots' per-asset price

Each `SessionValueSnapshot.positions` entry already persists `price` (set in
`record_value_snapshot` via `valuation.positions`). The current run's snapshot is
recorded before the push is built, so "today's price" is `snapshot.positions`.
"Yesterday's price" is the same field on the session's most recent **earlier**
snapshot.

Per held ticker: `daily_change = today_price / prior_price − 1`, matched by
ticker between the two snapshots. `_best_worst_line` is fed these values and is
otherwise unchanged.

### D2 — Reuse the existing prior-snapshot lookup

`paper_trading/service.py` already has a private `_prior_snapshot(session,
session_id, before)` returning the most recent snapshot strictly before a date
(it backs the header's daily P&L baseline). "Previous available snapshot" (not
literally yesterday) is exactly right — markets close on weekends/holidays and a
stocks-only session is not snapshotted on weekends. Expose a thin public accessor
(e.g. `get_previous_value_snapshot(session, session_id, before)`) over
`_prior_snapshot` so the snapshot job can fetch it and it is directly unit-testable.
`before` is the current snapshot's `snapshot_date`.

### D3 — Edge-case handling (observable in the push)

- **No earlier snapshot** (session's first daily report): no daily change is
  computable → omit the best/worst line entirely.
- **Holding absent from the earlier snapshot** (opened/first appeared today): no
  prior price → exclude that single asset from the candidate set; do not fabricate
  from avg-cost. Other holdings still compared.
- **Prior price missing or ≤ 0** for a ticker → exclude that ticker.
- **No comparable holding remains** after exclusions → omit the best/worst line.

The holdings list handed to `_best_worst_line` is built only from comparable
assets; when it is empty the line is already omitted by the existing
`if not holdings: return None`, so `_best_worst_line` needs no change.

### D4 — Per-session scope of the best/worst line (spec alignment)

The shipped push sends **one message per session** with that session's own
best/worst holding (the per-session split predates this change). The existing
`ai-paper-trading` spec sentence read "ranked by return across all snapshotted
sessions", which never matched the shipped per-session push. This change's MODIFIED
requirement describes the best/worst line as **per session** (the session's own
holdings), aligning the spec with the shipped behavior while making the metric
change. No code scoping behavior changes — only the metric and the edge cases.

## Risks / Trade-offs

- A holding first opened on the report day shows no performer figure that day.
  Accepted: a since-entry or fill-vs-close figure for a one-day-old position would
  reintroduce the cost-basis inconsistency the fix removes.
- The first report after a build/first snapshot omits the line. Accepted and
  expected (no prior day exists to measure against).

## Migration Plan

None — behavior-only change to notification assembly plus a new read-only service
accessor. No data migration, no backfill.

## Open Questions

None outstanding; edge-case choices above are the recommended defaults and are
surfaced in the proposal for review.
