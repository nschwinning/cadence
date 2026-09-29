## Context

See proposal.md — Why. The relevant current state:

- Daily EOD value snapshots already exist per session (`session_value_snapshots`: `snapshot_date`, `total_value`, …), written by the snapshot cron and read per-session via `GET /api/v1/paper-trading/sessions/{id}/value-history` (`service.list_value_history` → `list_value_snapshots`, ordered oldest-first).
- The session list read (`service.list_sessions`, `GET /sessions`) already supports the non-archived filter (`include_archived=false`, the default) and each `PaperTradingSessionRead` carries `allocated_capital`, `portfolio_name` (nullable), and `strategy_key`.
- The frontend already renders a single-session inline-SVG chart, `SessionValueChart.tsx` / `ValueCurve` (dependency-free, viewBox 800×160, `vector-effect="non-scaling-stroke"`, `<2`-point placeholder), and shares `Panel`, `lib/format.ts` (`formatCurrency`, `formatPercent`), and TanStack Query patterns in `api/paperTrading.ts`.
- There is **no** batch/multi-session value-history read today; the detail page fetches one session at a time.

## Goals / Non-Goals

**Goals:**
- One backend call returns the comparison series for all non-archived sessions.
- A list-page chart overlays those sessions with a %/$ toggle and a legend, reusing existing chart/format/Panel idioms.
- No schema or migration changes — read existing snapshots only.

**Non-Goals:**
- Benchmark overlay on the comparison chart (single-session chart keeps its benchmark; comparison chart compares sessions to each other, not to a benchmark).
- Interactive point tooltips, zoom, or date-range selection.
- Aligning sessions to a common t=0 origin — lines are plotted on the real calendar axis (see Decisions).
- Any change to the single-session detail chart, KPIs, snapshot cron, or DB.

## Decisions

**1. New batch endpoint over N per-session fan-out.** Add `GET /api/v1/paper-trading/sessions/value-history-comparison` returning one entry per non-archived session. Rationale: a single request is simpler for the list page than orchestrating N `useSessionValueHistory` hooks, avoids N round-trips as session count grows, and is straightforward to unit-test in the service. Alternative (fan-out N existing calls) was rejected: dynamic hook counts are awkward in React and it multiplies requests.
- Service: `list_sessions_value_comparison(db)` reuses `list_sessions(include_archived=False)` for membership and `list_value_snapshots(session_id=…)` per session for points. Reuses the existing `portfolio_name or strategy_key` label logic already exposed on the read model.
- Response schema (`api/schemas.py`): `SessionValueComparisonResponse { sessions: list[SessionValueComparisonSeries] }`, where `SessionValueComparisonSeries { session_id: UUID, label: str, allocated_capital: float, points: list[SessionValueComparisonPoint] }` and `SessionValueComparisonPoint { snapshot_date: date, total_value: float }`. Points carry only what both metrics need; return-% is derived client-side.

**2. Return-% is derived on the client, not stored/returned.** The endpoint returns raw `total_value` + `allocated_capital`; the frontend computes `(total_value − allocated_capital) / allocated_capital` per point. Rationale: keeps the payload minimal and the metric definition co-located with the toggle that switches it; matches how KPI `total_return_pct` is already defined (relative to allocated capital). Guard `allocated_capital > 0` (skip/return 0 otherwise) to avoid divide-by-zero.

**3. Plot on the real calendar axis with a shared x-domain.** All series share one x-domain = [min snapshot_date across sessions, max snapshot_date] and one y-domain per selected metric (min/max across all plotted series). Rationale: sessions started at different times; a shared calendar axis shows both *when* and *how well* each performed. Points map x by date position within the shared domain (not by raw index, since sessions have different point counts/dates). A session with `<2` points is excluded from plotting and domains but listed in the legend.

**4. New chart component rather than overloading `SessionValueChart`.** Add `SessionComparisonChart.tsx` (+ co-located test) mirroring the `SessionValueChart` inline-SVG idiom but drawing N colored polylines + a legend + the metric toggle. Rationale: `SessionValueChart` is single-series with a benchmark overlay and a fixed trend-color scheme; the comparison chart needs a categorical per-session palette and multi-series scaling — cleaner as a sibling than a branchy shared component. A small fixed categorical color palette (cycled if sessions exceed its length) is defined locally.

**5. Frontend data layer.** Add to `api/paperTrading.ts`: `listSessionsValueComparison()` → GET, `paperTradingKeys.valueComparison()` query key, and `useSessionsValueComparison()` hook (non-polling; snapshots are daily). Add matching types to `types/api.ts`. Wire the chart into `PaperTradingPage.tsx` above the Sessions card, inside a `Panel`.

## Risks / Trade-offs

- **Many sessions → crowded chart / color reuse.** → Cycle a categorical palette and rely on the legend; acceptable for a personal-scale app. Date-range/session filtering is a future enhancement, not in scope.
- **Sessions with sparse or misaligned snapshot dates** produce jagged lines. → Plot by actual date position on the shared axis so gaps read truthfully; `<2`-point sessions are legend-only.
- **Return-% and value views have very different y-scales.** → Each metric computes its own y-domain on toggle, so switching always rescales; no shared scale between the two views.
- **New endpoint cost scales with session count × snapshots.** → Non-archived sessions only, daily snapshots, single query per session reusing existing indexed reads; negligible at expected scale.

## Migration Plan

No migration. Additive read endpoint + additive frontend view. Deploy backend and frontend together; rollback is removing the endpoint and the chart with no data effects.
