## Context

See proposal.md — Why. Three surfaces disagree on what "P&L" means and the list
is never marked to market. Relevant existing seams (all already live-valuation
capable, no new endpoint needed):

- `backend/src/cadence/paper_trading/service.py`
  - `compute_session_value(...)` marks open positions to market via
    `broker.get_quotes` and returns per-position `unrealized_pnl`, cash, and
    `total_value` (net of fees).
  - `session_kpis(...)` already emits the live triple (current value / realised /
    unrealised) for the detail page.
  - `record_value_snapshot(...)` persists `SessionValueSnapshot.positions` with
    a per-position `unrealized_pnl` breakdown (the range-start unrealised source).
  - `ClosedPosition` carries `exit_date` + `realized_pnl`, indexed on
    `(session_id, exit_date)` — the range-realised source.
  - `session.total_pnl` is the cumulative closed-lot realised P&L.
- `backend/src/cadence/dashboard/service.py` — `_session_performance(...)` already
  computes KPIs per active session for the overview and emits current value, range
  ΔNAV P&L, and range fees; the range window `[range_start, range_end]` is already
  resolved here.
- Frontend: `useDashboardOverview`, `useSessions`, `useSessionKpis` are TanStack
  Query hooks; `useSessionOrderSync` already demonstrates a per-hook
  `refetchInterval`. `QueryClient` in `main.tsx` has no global default options.

## Goals / Non-Goals

**Goals:**

- One definition of the current-value / realised / unrealised triple across the
  Dashboard, Portfolios list, and session detail.
- Range-relative realised and unrealised on the Dashboard; all-time (`Max`) on the
  list and detail, which is the same formula evaluated over the full life.
- Live ~30s refresh of the three views with no new backend endpoint and no
  migration.

**Non-Goals (design-level):**

- No range selector added to the list or detail pages — they are fixed at the
  `Max`/all-time evaluation of the shared formula.
- No attempt to make realised + unrealised add up to range ΔNAV; the range return
  % stays the authoritative movement metric.
- No change to the EOD snapshot cron, the value-history chart, or the Sharpe /
  benchmark / drawdown KPIs.

## Decisions

### D1 — Range realised P&L = Σ closed-lot realised over the range

Compute per session as the sum of `ClosedPosition.realized_pnl` for lots whose
`exit_date` falls within `(range_start, range_end]`, reusing the
`(session_id, exit_date)` index. For the `Max` range this equals
`session.total_pnl` (the cumulative realised P&L already shown on the list/detail),
so the list/detail "all-time" value and the dashboard "`Max`" value are identical
by construction. _Alternative considered:_ deriving realised from snapshot deltas —
rejected; closed-lot rows are the exact, indexed source and already power the KPI
P&L series.

### D2 — Range unrealised P&L = live unrealised − range-start snapshot unrealised

Compute per session as `current_unrealised − baseline`, where `current_unrealised`
is `Σ(market_value − cost_basis)` on open positions from `compute_session_value`
(already computed for the overview), and `baseline` is the summed per-position
`unrealized_pnl` from the session's `SessionValueSnapshot` at or before
`range_start`. When no snapshot exists at/before the range start (new session, or
the `Max` range) the baseline is `0`, so the figure equals the current live
unrealised — matching the list/detail all-time value. _Accounting caveat (also in
the proposal + spec):_ positions opened and still held mid-range, or opened and
closed within the range, make "change in unrealised" a standard mark-to-market
delta rather than an additive component of ΔNAV; we present realised and
unrealised as two independent figures and never claim they sum to ΔNAV. _Alternative
considered:_ reconstructing a lot-level cost-basis snapshot at the range boundary —
rejected as far heavier for no meaningful gain over the snapshot baseline.

### D3 — List marks sessions to market via the existing valuation path

The Portfolios list read computes each row's current value + unrealised from
`compute_session_value` and realised from `session.total_pnl` (all-time). It does
**not** call the full `session_kpis` (which also computes Sharpe, the benchmark
buy-and-hold, and the time-weighted return) — those are detail-only costs. Prefer a
light shared helper that returns just the triple so the list endpoint stays cheap
per session while still being live. The dashboard overview already pays the
`compute_session_value` cost per active session, so the list paying it is
consistent and acceptable. _Alternative considered:_ a dedicated batch
valuation endpoint — rejected; the per-session mark-to-market is already O(sessions)
and the list is not large.

### D4 — Shared backend helper for the triple

Introduce one internal helper in `paper_trading/service.py` that, given a session
(and optionally a range window), returns `(current_value, realised, unrealised)`
using D1/D2, so the dashboard overview, the list read, and the detail KPIs derive
the triple from one place and cannot drift. The detail KPI summary keeps its
richer output; it sources the same three numbers from this helper.

### D5 — Live refresh is per-hook `refetchInterval ≈ 30000ms`

Add `refetchInterval: 30_000` to `useDashboardOverview`, `useSessions`, and
`useSessionKpis`, mirroring `useSessionOrderSync`. Rely on TanStack Query's default
`refetchIntervalInBackground: false` to pause when the tab is backgrounded. No
global `QueryClient` default is introduced, so other queries are unaffected. The
session detail's existing order-sync poll is left as-is and runs alongside this.
_Alternative considered:_ a websocket/SSE live feed — rejected as disproportionate;
30s polling over the already-live endpoints meets the "live feel" goal.

### D6 — Frontend consistency and the redundant header stat

`types/api.ts` mirrors the new fields (dashboard per-session range realised/
unrealised; session read current value / realised / unrealised). The Dashboard hero
tiles + leaderboard + `aggregate.ts` sum the per-session realised/unrealised
(simple dollar sums) alongside the existing money-weighted return. The Portfolios
list renders the triple columns, replacing the lone profit/loss column. The session
detail header's realised-only "Total P&L" `<dl>` stat is removed (the KPI row below
already shows the full triple), leaving Capital — so the page states P&L once.

### D7 — Dashboard scope legibility via scoped section bands (Direction A)

A design pass surfaced the core confusion: the range selector sits beside the
page `<h1>`, implying it governs the whole view, but it actually governs only the
range-scoped figures. The dashboard silently mixes three scopes — range-scoped
(realised/unrealised/return/fees, equity curve, failed runs, recent activity,
universe performers), point-in-time/live (current value/NAV), and
current-composition (universe balance) — with no visual cue. We adopt the chosen
**Direction A — scoped section bands**: scope is communicated by *where* a number
lives, so the reflow doubles as the explanation.

- **Three labelled bands** replace the flat stack:
  - **"Portfolio value"** band — holds the point-in-time current value/NAV,
    marked with a small live chip (reusing the existing `FreshnessBadge
    kind="live"`, the "● Live" emerald-dot pattern already on the session-detail
    KPIs), tooltip along the lines of "Marked to market against current quotes,
    updated every ~30s." This band does not change with the range.
  - **"Performance · over the past month"** band — the range selector is **docked
    inside this band's header** (moved off the page title), and the trailing
    phrase tracks the selector: `today / the past week / the past month / year to
    date / the past year / all time`. Holds realised/unrealised/return/fees and
    the equity curve.
  - **"Universe · as it stands now"** band — the current-composition balance
    stats (asset count, eligible/ineligible, sectors covered, top-sector share,
    top-category share).
- **Cross-cutting rule:** the universe best/worst performers are range-driven, so
  that sub-block carries its *own* "over the past month" range chip even inside
  the composition band — the one place two scopes legitimately coexist.
- **Hero tiles** split into a value group (live) and a performance group (range).
  The **leaderboard** gains a spanning sub-header ("Over the past month") over the
  range columns, and the Value column header keeps a single `●` live dot.

Reusing `FreshnessBadge kind="live"` (rather than inventing a dashboard-specific
indicator) keeps one mental model for "live" across detail and dashboard. The
specs state the observable behaviour (scope grouping, the range indication on
range-scoped sections, the live mark on the point-in-time value, the
current-composition mark, selector placement, and the universe-performer chip);
the exact band copy and chip wording are design-level and carried here, not pinned
in the spec, so microcopy can be tuned without a spec change. _Alternatives
considered:_ Direction B (per-figure scope badges) — rejected as visually noisy;
Direction C (two separate tabbed views) — rejected as over-fragmenting a single
glanceable overview. Effort is medium and frontend-only: reflow `DashboardPage`
into three sections with headers, split `HeroTiles` into value + performance
groups, add the spanning header + live dot to `PortfolioLeaderboard`, and add one
range chip to the universe performer sub-list. No backend change beyond the
already-planned range realised/unrealised fields.

## Risks / Trade-offs

- **List endpoint latency grows with session count** (each row now marks to
  market) → use the light triple helper (D3), not full KPIs; the dashboard already
  does equivalent work per active session, so the cost profile is known.
- **30s polling adds request volume** → background pause (D5) and the existing
  short-TTL live endpoints keep it modest; intervals are per-hook so easy to tune.
- **Unrealised-delta caveat could confuse** (realised + unrealised ≠ ΔNAV) → the
  spec and UI treat them as two independent figures; range return % remains the
  headline movement metric, and fees stay separate.
- **Range-start snapshot may be absent intraday on the first day of a range** →
  baseline falls back to 0 (documented), which for short ranges can momentarily
  read the unrealised as all-time; acceptable and self-corrects once a snapshot in
  the range exists.

## Migration Plan

No database migration. Backend additive fields on existing read/overview schemas;
frontend additive columns/tiles and per-hook polling. Deploy is backend-then-
frontend (frontend tolerates the new fields being present). Rollback is a straight
revert — no persisted state changes.
