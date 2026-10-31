# Design

## Context

See `proposal.md — Why`. Relevant current state:

- AI cost is read from the LiteLLM proxy's **separate** Postgres database
  (`settings.LITELLM_DATABASE_URL`), table `"LiteLLM_SpendLogs"`, via
  `paper_trading/ai_cost.py::session_ai_cost_usd(session_id)`. It sums `spend` WHERE
  `metadata->'spend_logs_metadata'->>'cadence_session_id' = :sid`, uses a cached read-only
  psycopg engine, and **degrades to `None`** when the DSN is empty or any error occurs
  (never raises). This is the only existing cost reader; it is strictly single-session.
- `dashboard/service.py::get_dashboard_overview(...)` is **range-scoped** (via the
  `DashboardRange` enum) and selects **ACTIVE sessions only** (`SessionStatus.ACTIVE`). It
  returns per-session performance rows that the frontend re-aggregates client-side.
- The frontend session-detail page renders the per-session tile as
  `data.ai_cost_usd === null ? '—' : formatCurrency(...)` with hint "Cost tracking
  unavailable" (null) / "Cumulative LLM cost this session" (value).

## Goals / Non-Goals

**Goals**
- All-time, per-portfolio AI cost (active sessions) with a grand total.
- One batched DB round-trip regardless of session count.
- Preserve the exact degradation contract (unavailable → null/em-dash; no-spend → 0).

**Non-Goals**
- No date-range filtering of cost (all-time only).
- No stopped/archived sessions in the breakdown (active only, matching the overview scope).
- No change to `/dashboard/overview`, its range/selection behavior, or the per-session tile.
- No new migration or DB column; `SpendLogs` is read-only and external.
- No reaction to the combined-equity chart's portfolio selection.

## Decision 1: Dedicated endpoint instead of extending `/overview`

The requested data is **all-time + range-independent** (over active sessions); `/overview`
is **range-scoped**. Extending `/overview` would (a) be semantically wrong (the panel must
not move with the range), and (b) tempt a per-session cost query inside the range loop. So
add a separate endpoint, e.g. `GET /api/v1/dashboard/ai-costs`, computed once.

Alternatives rejected:
- *Add `ai_cost_usd` to `DashboardSessionPerformance`*: couples all-time cost to the
  range-scoped, active-only overview; wrong scope and misleading.
- *Compute per-portfolio cost client-side*: the raw `SpendLogs` are in a separate DB the
  frontend cannot reach; aggregation must be server-side.

## Decision 2: Batched cost helper in `ai_cost.py`

Add `session_ai_costs_usd(session_ids: Sequence[str]) -> dict[str, float] | None` (name TBD
at apply) that issues **one** query:

```sql
SELECT metadata->'spend_logs_metadata'->>'cadence_session_id' AS sid, SUM(spend)
FROM "LiteLLM_SpendLogs"
WHERE metadata->'spend_logs_metadata'->>'cadence_session_id' = ANY(:sids)
GROUP BY sid
```

Degradation contract (must match `session_ai_cost_usd`):
- Empty `LITELLM_DATABASE_URL` → return `None` (source unconfigured; caller renders all
  costs as unavailable).
- Any query error → log a warning and return `None` (never raise).
- Reachable source: return a map of `sid → float(sum)`. Session ids **absent** from the map
  have **no recorded spend** and are rendered as `0`, distinct from the unavailable state.
- Empty `session_ids` → return `{}` without touching the DB.

The existing `session_ai_cost_usd` stays unchanged (still used by session KPIs).

## Decision 3: Null vs zero semantics (end to end)

- **Source unavailable** (helper returned `None`): each portfolio row's cost is `null`, the
  total is `null`; frontend renders "—" + "Cost tracking unavailable".
- **Source reachable, session not in map**: cost is `0`; frontend renders `$0.00`.
- Total, when the source is reachable, is the sum of the numeric per-portfolio costs.

This mirrors the session-detail tile exactly, so the two cost surfaces read consistently.

## Backend shape

- `dashboard/service.py`: new frozen dataclasses, e.g.
  - `PortfolioAiCost(session_id: str, label: str, ai_cost_usd: float | None)`
  - `DashboardAiCosts(portfolios: list[PortfolioAiCost], total_ai_cost_usd: float | None)`
  - New function `get_dashboard_ai_costs(session) -> DashboardAiCosts`: list **active**
    sessions via `paper_trading_service.list_sessions(session, status=SessionStatus.ACTIVE,
    ...)` (reuse the overview's high limit), take the portfolio display label the dashboard /
    paper-trading pages already use, call the batched helper once, and assemble rows + total
    per Decision 3. Rows sorted by cost descending (nulls/absent treated as lowest).
- `api/schemas.py`: `DashboardPortfolioAiCostRead` + `DashboardAiCostsRead` mirroring the
  dataclasses; explicit mapping in the router.
- `api/routers/dashboard.py`: `GET /dashboard/ai-costs` → `DashboardAiCostsRead`. No `range`
  param. Depends on `db` only (no broker needed — cost comes from `SpendLogs`).

## Frontend shape

- `types/api.ts` (Dashboard section): `DashboardPortfolioAiCost { session_id; label;
  ai_cost_usd: number | null }` and `DashboardAiCosts { portfolios[]; total_ai_cost_usd:
  number | null }`.
- `api/dashboard.ts`: `getDashboardAiCosts()` + `useDashboardAiCosts()` (query key under
  `dashboardKeys`, `refetchInterval: 30_000`), a **separate** fetch from the overview.
- New component (e.g. `components/dashboard/AiCostBreakdown.tsx`): table of label + cost
  rows (sorted desc, provided by backend but defensively re-sortable), a total row, the
  em-dash/`$0.00` convention, the "Cost tracking unavailable" hint when the total is null,
  and an empty state. Reuse `formatCurrency` from `lib/format.ts` and existing panel
  styling (Tailwind).
- `DashboardPage.tsx`: render the panel **above the market-performers tiles** — directly
  above the Universe section's best/worst performers (`UniversePerformers` within
  `UniverseSection`) — in its own band/section (not under "Performance · {range}"),
  independent of `range` and `selectedIds`.

## Risks / Trade-offs

- **`ANY(:sids)` parameter binding** with psycopg3 — ensure the id list binds as an array;
  fall back to an `IN (...)` expansion if needed. Covered by a unit test that asserts a
  single grouped query.
- **Label source**: must match what the dashboard/paper-trading list shows for a portfolio;
  reuse the existing label field rather than re-deriving, to avoid drift.
- **Session scope** is active-only (confirmed at review); the session-selection filter in
  `get_dashboard_ai_costs` uses `SessionStatus.ACTIVE`, matching the overview.

## Migration / Deploy

None. Read-only against the existing LiteLLM `SpendLogs`. The panel shows real figures only
when `LITELLM_DATABASE_URL` is set and the `litellm` DB is reachable (same precondition as
the per-session tile); otherwise it degrades to "—" / "Cost tracking unavailable".
