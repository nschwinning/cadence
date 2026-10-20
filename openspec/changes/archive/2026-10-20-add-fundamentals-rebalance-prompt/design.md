## Context

See proposal.md — Why. The rebalance flow already loads its prompt from a
versioned, append-only `rebalance_prompt` table and **freezes** the active version
onto each session at build time (`rebalance_prompt_version`). The current latest
REBALANCE version is **3** (the trend-trading prompt). Fundamentals are stored per
stock in `AssetFundamentals` (1:1 with `Asset`, JSONB `document`) and populated for
all `category=stock` assets by the existing quarterly SEC EDGAR refresh. The
`document["figures"]` map holds latest-annual (FY/10-K) values keyed as `revenue`,
`gross_profit`, `operating_income`, `net_income`, `operating_cash_flow`,
`eps_basic`, `eps_diluted` (each `{value, unit, fiscal_year, period_end, form}`);
`status` is `available` / `partial` / `unavailable`. The candidate/holding objects
handed to the agent are built in `ai_portfolio/_helpers.py`
(`_candidates_from_universe`, `_build_holdings`) and already carry extra per-asset
data (`indicators`, `reversal_flags`) that rides inside `candidates_json` /
`holdings_json`.

This change follows the project's **opt-in** convention: fundamentals are a
per-session flag (`use_fundamentals`, default off) frozen at build and surfaced on
reads and in the UI, exactly like `use_technical_indicators`, `stop_loss_enabled`,
`risk_guardrails_enabled`, and `learning_feedback_enabled`. Unlike learning
feedback, the opt-in carries **no dependent parameter** (no window/threshold), so
it is the simplest possible opt-in: a bare boolean.

## Goals / Non-Goals

**Goals:**
- Add REBALANCE prompt **v4** that documents and consumes a per-ticker fundamentals
  block on candidates and holdings, using the existing freeze-per-session machinery.
- Make fundamentals a **per-session opt-in (default off)** plumbed end to end
  (column, params, API, build form toggle, session read field, fact tile).
- Keep the whole feature backward-compatible: sessions frozen on v1–v3 and
  opted-out v4 sessions are byte-for-byte unchanged in what the agent receives.
- No extra run-time data fetch; derive everything from already-stored figures.

**Non-Goals (design-level):**
- No new `{token}` in the input template — fundamentals ride inside the existing
  `candidates_json` / `holdings_json`, so `_build_rebalance_input` keeps its signature.
- No price-derived ratios, growth, or leverage (data not available); no build-prompt
  or crypto-prompt change; no dependent opt-in parameter.

## Decisions

### D1: Attach fundamentals inside the candidate/holding objects, not as a new prompt block
The data rides inside `candidates_json` / `holdings_json` exactly as `indicators`
does today. **Why:** zero change to `_build_rebalance_input` / `_render`; the v4
template stays structurally identical to v3 (only the *instructions* text must
document the new field). Alternative — a dedicated `{fundamentals_json}` token and a
new block renderer (like `_recent_outcomes_block`) — was rejected as more surface
area for no behavioral gain.

### D2: Gate on the opt-in AND a new `FUNDAMENTALS_PROMPT_VERSION = 4` constant
Mirror the trend gate: the block is assembled and attached only when
`use_fundamentals AND version >= FUNDAMENTALS_PROMPT_VERSION`, where `version` is
the active prompt version at build (`flows/build.py`) and the session's frozen
`rebalance_prompt_version` at rebalance (`flows/rebalance.py`). **Why:** matches the
established version-dispatch pattern (`TREND_PROMPT_VERSION` + the opt-in flag);
keeps older frozen sessions and opted-out sessions untouched. The version check
guards against a session somehow carrying the flag while frozen on a pre-v4 prompt.

### D3: v4 instructions are worded DEFENSIVELY ("when present")
The seeded v4 `_V4_INSTRUCTIONS` SHALL describe the fundamentals object as optional
per-ticker data to weigh **when present**, tolerating its absence. **Why:** an
opted-out session can still be frozen on v4 (if v4 is the active version at its
build), and will receive candidates/holdings with **no** fundamentals attached.
The trend v3 prompt is NOT written this way (its text assumes indicators are always
there), which is a latent wart; v4 avoids replicating it so an opted-out v4 session
reads cleanly. The v4 `_V4_INPUT_TEMPLATE` is the v3 template verbatim (per D1).

### D4: A pure, unit-testable derivation helper
A standalone pure function maps `document["figures"]` → the margins/EPS/scale
sub-object (or an "unavailable" marker). **Why:** isolates the margin math and the
divide-by-zero / missing-field / non-`available`-status handling for direct unit
testing, independent of the DB or agent.

### D5: Eager-load `Asset.fundamentals` to avoid N+1
`list_assets` (`assets/service.py`) is a plain `select(Asset)` and lazy-loads the
relationship; accessing `asset.fundamentals` per candidate would trigger N+1. Add
`selectinload(Asset.fundamentals)` on the universe query used by build/rebalance.
**Decision:** always eager-load (one extra bulk query) rather than branch the query
on the gate — simpler, and the cost is a single `IN` query regardless of version or
opt-in state.

### D6: `use_fundamentals` is a bare boolean opt-in, mirroring `learning_feedback_enabled`
New non-nullable `use_fundamentals` column on `paper_trading_sessions` (default /
`server_default` false), threaded through `AIBuildParams`, `create_session`, the
build request + session read schemas, the router's request→params mapping, the
build-form toggle, and a session-detail fact tile. **Why:** this is the project's
uniform opt-in shape; `learning_feedback_enabled` is the closest precedent (a
boolean), except fundamentals needs no companion parameter, so no `*_window`
analogue is added.

## Risks / Trade-offs

- **Token budget growth** → The block is a compact fixed set of figures per ticker,
  not raw EDGAR facts; only attached for opted-in sessions; candidate counts are
  already bounded by the universe + discovery caps.
- **Stale / partial fundamentals** → The quarterly refresh may lag; `status != available`
  and missing figures both degrade to the "fundamentals unavailable" marker (or an omitted
  margin), so the agent never sees fabricated numbers. The spec makes this observable.
- **Seed-text drift from v3** → Covered by a byte-for-byte seed-equivalence test on the
  v4 template (the existing v3 test pattern), so an accidental template change is caught.
- **Eager-load on every build/rebalance** → One extra bulk query even for opted-out
  sessions; negligible versus the agent run, and avoids query-shape branching.

## Migration Plan

1. Deploy the code (constant + helper + gate + eager-load + opt-in plumbing) with
   two Alembic migrations: one adding the `use_fundamentals` column (default false),
   one seeding REBALANCE prompt v4. `alembic upgrade head` applies both; existing
   rows backfill to `use_fundamentals = false`.
2. New builds that opt in freeze v4 and `use_fundamentals = true`; existing and
   opted-out sessions keep their frozen version and receive no fundamentals block.
3. **Rollback:** `alembic downgrade` removes the v4 seed row and the column. Any
   session already frozen on v4 would then fail to load its prompt — so rollback
   should pair with not having built v4 sessions, or re-seeding v4. (Append-only
   history means forward-fix is preferred.)
