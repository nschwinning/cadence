## Context

See proposal.md — Why. This adds a persisted, AI-authored assessment of the whole
asset universe to the Assets page, below the composition donuts.

Relevant existing structure (from a codebase survey):

- The backend has **no free-text LLM path**. All generation goes through
  `cadence.agents.build_agent(...)` (the `openai-agents` SDK), which *requires* a
  Pydantic `output_type`. The recommender (`recommendations/agent.py`:
  `RecommenderAgent` Protocol + `OpenAIRecommenderAgent` + `FakeRecommenderAgent`)
  is the template: an injectable Protocol seam, `asyncio.run(Runner.run(...))` under
  a timeout, a fake for tests, and a router DI factory.
- The `assets` domain is `models.py` / `service.py` / `errors.py` with a thin router
  at `api/routers/assets.py` and shared Pydantic schemas in `api/schemas.py`.
- Alembic head is `e9f0a1b2c3d4` (add_fractionable_to_assets).
- There is **no nightly in-place refresh of `Asset` rows**. The daily cron
  (`POST /ai-portfolio/rebalance-daily`) only appends to the separate
  `price_history` table via `ingest_latest`. `Asset` metric columns
  (`market_cap_usd`, `avg_daily_turnover_usd`, `history_years`, `is_eligible`,
  `criteria_results`) are written only at add/re-add time.
- The Assets page (`frontend/src/pages/assets/AssetsPage.tsx`) renders the two
  composition donuts (`components/dashboard/BreakdownTile.tsx`, fed by
  `useDashboardMetrics()`) at ~lines 452–467; the new panel goes immediately below.
- The frontend has **no markdown renderer** (no react-markdown/remark in
  `package.json`).

## Goals / Non-Goals

**Goals:**

- One persisted, current evaluation; replaced on each generation.
- Deterministic staleness detection via a universe content fingerprint.
- Reuse the established agent seam + fake so tests run offline.
- No new frontend dependency.

**Non-Goals:**

- Evaluation history / versioning (single current row only).
- Background/polling execution (generation is a single-shot, tool-less call).
- Per-asset AI commentary; this evaluates the universe as a whole.
- Changing what the nightly cron writes.

## Decisions

### Structured agent output, not raw markdown

Because `build_agent` forces a Pydantic `output_type`, the evaluation agent returns
`UniverseEvaluationOutput { narrative: str, strengths: list[str], concerns:
list[str], suggestions: list[str] }`. The spec's "markdown narrative + bulleted
findings" is realized as a prose `narrative` plus three finding arrays. Alternative
(raw markdown string) rejected: it fights the SDK's structured-output contract and
would need markdown parsing/sanitization on the frontend.

A new agent seam `UniverseEvaluationAgent` (Protocol) + `OpenAIUniverseEvaluationAgent`
lives in the `assets` package, mirroring `recommendations/agent.py`. It uses **no
tools** (no web search — it assesses the supplied universe summary only), runs via
`asyncio.run(Runner.run(agent, prompt, max_turns=1))` under
`asyncio.wait_for(timeout=...)`. Model reuses `settings.RECOMMENDER_MODEL` (no new
config key; a dedicated `ASSET_EVALUATION_MODEL` can be split out later). A
`FakeUniverseEvaluationAgent` in `tests/fakes.py` returns a canned output and
records calls; the router exposes `get_universe_evaluation_agent()` for test
override.

### Prompt is built from a universe summary, not raw rows

`service.py` builds a compact summary — counts by category and by sector,
eligibility counts, the largest sector/category concentrations, total count, and the
foreign/unpriceable listings (NULL `alpaca_symbol`) — and passes it as the prompt
input. Keeps token use bounded and the agent focused on structure, not per-row data.

### Staleness via a content fingerprint (chosen semantics: "any asset change")

The `assets` table has **no `updated_at`** column, so a timestamp watermark is not
available. Instead, `_universe_fingerprint(assets)` is a SHA-256 over a canonical,
ticker-sorted serialization of every asset's mutable attributes (ticker, name,
category, sector, exchange, currency, country, is_eligible, market_cap_usd,
avg_daily_turnover_usd, history_years, alpaca_symbol, fractionable,
criteria_results). Stored with the evaluation; recomputed on read; differ ⇒
outdated.

This realizes the operator's "any asset change" choice: it flips on membership
changes **and** on any edit to an existing asset (re-add metrics, eligibility). Note
(correcting the premise shown at decision time): there is no nightly `Asset`-row
refresh in this system, so in practice the evaluation goes outdated on universe
edits, not on a nightly schedule. The fingerprint deliberately excludes
price-history-derived values so daily price moves do not flip it. Alternatives
rejected: membership-only hash (misses metric/eligibility edits the operator asked
to catch); adding an `updated_at` column + touching every writer (more invasive,
and still needs a watermark compare).

### Server-side lazy-fill in GET; refresh via POST

`GET /assets/universe-evaluation` returns the current evaluation with a freshly
computed `outdated` flag; when none exists and the universe is non-empty, it
generates, persists, and returns it ("filled once when empty"). `POST
/assets/universe-evaluation/refresh` always regenerates and replaces the single row,
returning it as not-outdated. An empty universe returns a null evaluation and does
**not** call the agent. One generation code path (`service.generate_evaluation`)
backs both. For a single-operator app the GET side-effect and the small
concurrent-first-load double-generate window are acceptable (single row, last write
wins); a bounded agent timeout caps GET latency. Alternative (pure GET + client
fires refresh on null) rejected to keep "filled once when empty" a true backend
guarantee and the frontend trivial.

### Persistence: a single-row table

New model `AssetUniverseEvaluation` (table `asset_universe_evaluation`): `id`,
`narrative` (Text), `strengths`/`concerns`/`suggestions` (JSONB), `fingerprint`
(String, not null), `model` (String, nullable), `generated_at` (timezone-aware
DateTime). The service keeps at most one row (update-in-place if present, else
insert). New Alembic migration chains `down_revision = "e9f0a1b2c3d4"`.

### Frontend: structured render, no markdown dep

`UniverseEvaluationPanel.tsx` renders the `narrative` as paragraphs (split on blank
lines) and each finding array as a labelled `<ul>`. Shows `generated_at`, an
outdated warning badge when `outdated`, and a Refresh button (disabled + spinner
while the mutation runs). On first load, the GET's loading state shows a "generating"
message (the GET performs the one-time fill). New typed client
`api/assetEvaluation.ts` (read query + refresh mutation) and types in
`types/api.ts`. Alternative (add react-markdown) rejected: unnecessary given
structured output, and avoids sanitizing LLM-authored HTML.

## Risks / Trade-offs

- **GET has a side effect and can block on the agent** → bound it with
  `asyncio.wait_for`; only the first call (empty state) generates, so steady-state
  GETs are cheap.
- **Concurrent first loads could generate twice** → single-row upsert makes the last
  write win; negligible in a single-operator app.
- **Agent/provider outage** → `generate_evaluation` raises a domain error mapped to
  HTTP 502; the existing row (if any) is left untouched, and the panel surfaces the
  error without losing prior content.
- **Fingerprint schema drift** → if the hashed field set changes in a later release,
  existing evaluations read as outdated once (a one-time, self-healing refresh).
- **Prompt/float formatting nondeterminism in the fingerprint** → use a fixed,
  explicit serialization (sorted keys, repr-stable floats) so equal universes hash
  equal across processes.

## Migration Plan

1. Add the `AssetUniverseEvaluation` model + Alembic migration (`down_revision =
   e9f0a1b2c3d4`); verify `upgrade head` / `downgrade` round-trip and `alembic
   check`.
2. Ship backend (agent seam, service, schemas, routes) and frontend (client, panel,
   types) together.
3. No backfill: the table starts empty and self-fills on first Assets-page load.
4. Rollback: `downgrade` drops the table; the feature is additive, so removing the
   routes/panel leaves the rest of the app unaffected.
