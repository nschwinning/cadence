## Context

Both recommenders (`RunTarget.UNIVERSE` and `RunTarget.WATCHLIST`) are the single
`OpenAIRecommenderAgent`. Its `_run` builds the agent via `build_agent(...)`
without a `model=` argument, so `build_agent` falls back to
`settings.RECOMMENDER_MODEL` (`gpt-5-mini`). `build_agent` already accepts an
optional `model` override — it is simply never passed on this path.

A reusable catalog already exists: the `AIModel` StrEnum + `AI_MODEL_DISPLAY_NAMES`
in `paper_trading/constants.py`, surfaced by `GET /api/v1/paper-trading/models` as
`[{id, name}]`. Paper-trading sessions already select a model per session with it.
`AIModel.GPT_5_MINI` (`"gpt-5-mini"`) is the enum member matching the configured
`RECOMMENDER_MODEL` default, so the default already maps to a catalog member.

## Goals / Non-Goals

**Goals**
- Per-run, immutable model selection for both recommenders, chosen at run-create.
- Persist and surface the model each run used; backfill existing runs.
- Reuse the shared `AIModel` catalog — no parallel model list.
- Back-compatible: requests omitting `model` behave exactly as today.

**Non-Goals**
- The universe-**evaluation** agent (`assets/universe_agent.py`) — unchanged.
- Per-model pricing/cost display, A/B, or ensembling.
- Changing when/how recommendations run, the web-search tooling, prompt builders,
  `output_type`, timeouts, max-turns, or the catalog contents.

## Decisions

### D1 — Per-run selection, validated against the shared `AIModel` catalog
`RecommendationRunCreate` gains `model: AIModel | None = None`. Typing it as the
`AIModel` enum makes FastAPI/Pydantic reject an unknown id with 422 automatically
and keeps validation in one place. The router/service resolves `None` to the
configured default (see D2). The model is fixed at create time and never changes.

### D2 — Default resolution to `settings.RECOMMENDER_MODEL`
When the request omits `model`, the service resolves it to
`settings.RECOMMENDER_MODEL`. The configured default is expected to be a catalog
member (`gpt-5-mini` → `AIModel.GPT_5_MINI`); the resolver stores the raw
configured string so an operator who points `RECOMMENDER_MODEL` at a
not-yet-catalogued model still works (the enum only gates *request-supplied*
models, never the configured fallback). Resolution happens server-side so the API
contract stays "omit = default" rather than forcing the client to echo the
default.

### D3 — Persist on `RecommendationRun`, non-nullable with a server_default backfill
Add `model: Mapped[str] = mapped_column(String, nullable=False)`. The Alembic
migration adds the column with a `server_default` of the configured default model
string so existing rows backfill to it; the migration then drops the
`server_default` so future inserts must supply the value explicitly (matching how
the app always resolves a concrete model). Stored as the plain string (the enum
`.value`), consistent with how the session stores its model.

### D4 — Thread the model through the existing seam
`RecommenderAgent.recommend(...)` and `OpenAIRecommenderAgent._run(...)` gain a
`model: str` parameter, passed into `build_agent(model=...)`. `execute_run` reads
`run.model` (persisted at `create_run`) and passes it to `agent.recommend(...)`.
`background.py` needs no new field — the model is already on the persisted run row
by the time the job reads it. `StubRecommenderAgent` and the test fakes gain the
same parameter (recording it for assertions) to stay protocol-compatible.

### D5 — Reuse `GET /api/v1/paper-trading/models` on the frontend
The recommend and watchlist forms fetch the existing catalog endpoint rather than
adding a recommender-scoped one. The `AIModel` catalog living in the
`paper_trading` package is accepted as shared app config; the recommendations
schema imports `AIModel` from there. (Noted as acceptable coupling; extracting the
catalog to a neutral module is out of scope.)

## Risks / Trade-offs

- **Catalog coupling to `paper_trading`** — importing `AIModel` across packages is
  a minor coupling; accepted over duplicating the list (D5).
- **Configured default outside the catalog** — tolerated by D2: the enum gates
  only request input, so an off-catalog `RECOMMENDER_MODEL` still runs and is
  stored verbatim.
- **Non-nullable column on an existing table** — mitigated by the `server_default`
  backfill in the migration (D3).

## Migration Plan

New Alembic migration (down_revision = current head): add
`recommendation_runs.model` as `String NOT NULL` with `server_default` = the
configured default model string, then drop the `server_default`. Downgrade drops
the column. Round-trip verified in the apply gate.

## Open Questions

- None blocking. The configured default is assumed to remain a catalog member;
  D2 tolerates it not being one.
