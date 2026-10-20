## Context

See proposal.md — Why. The relevant current state:

- Assets carry an `Asset.membership` column (StrEnum `AssetMembership`,
  `universe` / `watchlist`; `assets/category.py`, column at `assets/models.py`).
  Membership is orthogonal to eligibility.
- `assets_service.list_assets(session, ...)` defaults `membership=AssetMembership.UNIVERSE`
  via `_filters`, so every caller that omits the arg gets universe-only assets.
  Passing `membership=None` removes the membership predicate and returns all assets.
- The AI candidate universe is assembled once, in `ai_portfolio/flows/rebalance.py`
  (the `list_assets(session)` call plus the in-Python scope/quarantine comprehension).
  A build creates only a portfolio+session shell and triggers the opening allocation
  as an **inline initial rebalance** through this same flow, so the rebalance flow is
  the single choke point governing both the opening allocation and every daily rebalance.
- Per-session frozen opt-ins already follow a fixed end-to-end shape
  (`use_fundamentals`, `use_technical_indicators`, learning feedback, stop-loss,
  guardrails): ORM boolean column → migration → `create_session` kwarg →
  `AIBuildParams` field + `to_payload`/`from_payload` → build flow → request schema →
  router mapping → read schema → rebalance-flow consumption → frontend type + toggle +
  fact tile.

## Goals / Non-Goals

**Goals:**

- Add one per-session frozen boolean, `include_watchlist` (default off), chosen at
  build time, that broadens the rebalance candidate universe to the union of
  `universe` and `watchlist` membership when on.
- Reuse the established frozen-opt-in shape end to end so the change reads like its
  siblings (fundamentals/learning feedback) at every layer.

**Non-Goals:**

- No change to `assets` service defaults — callers that omit `membership` still get
  universe-only. The broadening is local to the rebalance flow.
- No change to how the watchlist is curated (watchlist-targeted recommendation runs,
  membership assignment) or to the `assets` capability spec.
- No relaxation of any downstream gate (asset scope, quarantine, trend gate,
  eligibility, unexecutable-ticker exclusion) for watchlist assets.
- No post-build mutability of the flag (frozen, like its siblings).

## Decisions

**Flag name `include_watchlist`.** Reads as a boolean at every layer and matches the
union semantics ("include watchlist assets in the candidate universe"). Consistent
across column, params, schemas, and TS types.

**Consume via `list_assets(membership=None)` when enabled, not a post-query predicate.**
In `rebalance.py`, read `watchlist_enabled = bool(session_row.include_watchlist)`
(mirroring the `fundamentals_enabled` read) and call
`assets_service.list_assets(session, membership=None)` when enabled, else the current
`list_assets(session)`. Rationale: the membership filter already lives in `_filters`
and is the canonical place to select membership; querying all-membership and letting
the **existing** scope/quarantine/trend/eligibility gates run unchanged keeps watchlist
assets subject to exactly the same treatment with no duplicated filtering logic.
Alternative considered — keep the universe-only query and union in a second
`watchlist`-only query, or add a membership check to the `:303-307` scope comprehension:
rejected as more code and a second place membership semantics could drift. The re-query
site in the flow gets the same treatment so candidates and the re-query agree.

**Freeze at build, consume at rebalance only.** The build flow records
`include_watchlist` onto the session row via `create_session` and attaches nothing
itself (it has no candidate assembly — the opening allocation is an initial rebalance).
This matches the fundamentals precedent where build.py only persists the flag. The
spec's ADDED requirement states this explicitly so build-only persistence is not read
as a deviation.

**Non-nullable column, `server_default="false"`.** Same shape as `use_fundamentals`
(`Boolean, nullable=False, default=False, server_default="false"`). Pre-existing rows
backfill to false, so legacy sessions keep universe-only candidate universes with no
data migration beyond the column default.

## Risks / Trade-offs

- [A watchlist asset that is out-of-scope or ineligible could leak into candidates] →
  Mitigation: we broaden only the membership query; the asset scope, eligibility,
  quarantine, and trend gates run unchanged afterward, and a spec scenario asserts an
  out-of-scope watchlist asset is still excluded. Covered by a dedicated test.
- [Larger candidate set increases prompt size / token cost for opted-in sessions] →
  Accepted: watchlists are small and curated; the opt-in defaults off, so cost only
  grows when a user explicitly asks for it.
- [Freezing means a user can't add watchlist consideration to an existing session] →
  Accepted and intentional: matches every sibling opt-in; a user rebuilds to change it.

## Migration Plan

- Additive Alembic migration adds `paper_trading_sessions.include_watchlist`
  (Boolean, non-null, `server_default="false"`), chaining `down_revision` from the
  current head `a1c3e5f7b9d2`. Round-trips cleanly (drop column on downgrade).
- No backfill job needed — the server default covers existing rows.
- Fully backward compatible: default off reproduces today's behavior.
