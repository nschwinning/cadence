## Context

See proposal.md — Why. All AI reasoning (opening allocation and daily rebalance) currently calls the agent with `model=settings.AI_PORTFOLIO_MODEL`, a single process-wide string. There is no per-session choice and no per-run record of which model ran. The codebase already has a proven end-to-end pattern for exactly this shape of feature — the **benchmark catalog** and the per-session frozen opt-ins (`benchmark`, `use_fundamentals`, `use_technical_indicators`, stop-loss, guardrails): a server enum + display map, a catalog read endpoint, an enum-typed request field (auto-422), a frozen non-nullable session column with a `server_default` backfill, and a read field surfaced in the UI. This change mirrors that pattern rather than inventing a new one.

Since the `route-initial-allocation-through-rebalance` change, the rebalance path drives **both** the opening allocation and daily rebalances, and the build agent path is dead code. So threading the model through the rebalance seam alone covers every live AI run.

## Goals / Non-Goals

**Goals:**
- A fixed server catalog of selectable models, read over HTTP, with an unknown id rejected (422) exactly as an unknown benchmark is.
- The chosen model frozen on the session at build time and used for every AI run of that session.
- Each AI run records the model that produced it, surfaced on run detail — enabling per-run model attribution.
- Zero behavior change for existing sessions: they keep running on today's default model via a `server_default` backfill.

**Non-Goals:**
- Changing a session's model after build (no "switch model" control — unlike benchmark, the model is attribution-critical and must stay fixed; this mirrors the frozen opt-ins, not the switchable benchmark).
- Per-run model override independent of the session.
- Validating that a catalog id is actually a model the provider will accept at call time (the catalog is curated by the server; a bad entry is an ops concern, not a request-time check).
- Adding the model to any learning/analytics JSON document (`run_stats`, daily-run snapshot) in this change — recording is via a dedicated scalar column only.

## Decisions

**1. Fold the model catalog into `ai-paper-trading`, not a new capability.** The benchmark catalog lives inside `ai-paper-trading` (requirement "Benchmark index catalog") and is served from the paper-trading router. The model catalog is the same kind of thing; a standalone capability would fragment the spec. New endpoint `GET /paper-trading/models` returns `ModelCatalogEntry{id,name}`, mirroring `GET /paper-trading/benchmarks`.

**2. `AIModel` as a `StrEnum` in `paper_trading/constants.py`** beside `Benchmark`, with a display-name map and accessor (mirroring `BENCHMARK_DISPLAY_NAMES`/`benchmark_display_name`). Typing the build request field `model: AIModel | None` gives automatic 422 on an unknown id — identical mechanism to benchmark — so no hand-written validation.

**3. Frozen non-nullable `model` column on `paper_trading_sessions`**, threaded `AIBuildParams.model` → `create_session`, with the default resolved in the router (`model = payload.model.value if payload.model is not None else settings.AI_PORTFOLIO_MODEL`), mirroring the benchmark default resolution. **Key distinction — the migration backfill value is NOT the new configured default.** The Alembic migration (down_revision `e8f3a1c5d2b4`, the current head) adds the column with `server_default=sa.text("'gpt-5-mini'")` so existing rows backfill to the model those sessions actually ran on (`gpt-5-mini`), then (matching the benchmark/fundamentals column migrations) the column is non-nullable. Meanwhile the *configured default for new builds* (`settings.AI_PORTFOLIO_MODEL`) becomes `gpt-6-luna` (Decision 6), so a new build that omits a model is written with `gpt-6-luna` explicitly by the router. The DB column's ongoing server_default is immaterial to new rows (the router always writes model explicitly); it exists only to backfill the pre-existing rows correctly. The user confirmed all existing sessions ran on the same model, so a single backfill literal is correct — no per-row logic.

**4. Thread the frozen model through the rebalance seam only.** `flows/rebalance.py` already reads the session row's frozen fields; read `session_row.model` there and pass it through `agent.rebalance(...)` → `rebalance_ai_portfolio(...)` → `_run_rebalance(...)`, replacing the hardcoded `settings.AI_PORTFOLIO_MODEL` at the agent build site. Fall back to `settings.AI_PORTFOLIO_MODEL` when the value is somehow absent (defensive; the column is non-null). The dead build agent path is left untouched.

**5. Per-run model recorded as a scalar column on `ai_portfolio_events`**, set at event finalization (`_finish_event`), not stuffed into `run_stats` (which is intentionally UI-hidden). A second small migration adds `ai_portfolio_events.model` as nullable (historical events have no recorded model). Surfaced via the run-detail read.

**6. Starter catalog confirmed with the user (2026-10-20): `gpt-5-mini`, `gpt-5.6-luna`, `gpt-6-luna`; new default `gpt-6-luna`.** The user asked for a couple of small, fast, cheap models from the gpt-5.6/gpt-6 series; those series dropped the "mini" name, and the cheapest/fastest tier in each is "Luna" (per the Oct 2026 OpenAI API lineup), so the two added models are the Luna tier of each series. The configured default (`config.py` `AI_PORTFOLIO_MODEL`) changes from `gpt-5-mini` to `gpt-6-luna`. `gpt-5-mini` stays in the catalog because existing sessions ran on it and are backfilled to it (Decision 3). The catalog is extended later by adding `AIModel` members.

## Risks / Trade-offs

- **[Catalog id must match the real provider model string]** → Catalog ids are the actual model strings passed to the agent (as `AI_PORTFOLIO_MODEL` is today), so a typo would fail live calls. Mitigation: seed the catalog from the known-good configured default and require user sign-off on any additional ids before apply.
- **[The configured default must be a catalog member]** → If `AI_PORTFOLIO_MODEL` were not in the catalog, a build omitting a model would persist an unselectable id. Mitigation: the catalog includes the new configured default `gpt-6-luna` AND the backfill value `gpt-5-mini` (both asserted by a test).
- **[Two migrations in one change]** → session column + event column. Mitigation: both are additive; chain the event-column migration after the session-column one; round-trip test upgrade/downgrade.
- **[Non-null session column vs. legacy rows]** → `server_default` backfills every existing row before the non-null constraint applies, so no legacy row is left null. The agent-side fallback is belt-and-suspenders.

## Migration Plan

1. Change `config.py` `AI_PORTFOLIO_MODEL` to `gpt-6-luna` (new default for builds that omit a model + the agent fallback). Apply the session-column migration (adds `model` with `server_default='gpt-5-mini'`, non-nullable) — existing sessions backfill to `gpt-5-mini` (the model they ran on), so their attribution is unchanged while new builds default to `gpt-6-luna`.
2. Apply the event-column migration (adds nullable `model`) — historical events read null; new runs record their model.
3. No data backfill needed for events; no ops step.
4. Rollback: both migrations are reversible drops; the agent falls back to `settings.AI_PORTFOLIO_MODEL`, so dropping the columns restores exact current behavior.

## Open Questions

- None. Catalog membership and the default id were confirmed with the user on 2026-10-20 (see Decision 6): default `gpt-5-mini` (unchanged), plus `gpt-5.6-luna` and `gpt-6-luna`.
