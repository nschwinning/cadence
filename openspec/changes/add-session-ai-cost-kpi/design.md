## Context

See proposal.md — Why. The relevant current state this design builds on:

- `add-litellm-model-proxy` added the gateway seam. `agents/gateway.py::llm_trace(trace_id)` sets a ContextVar; `run_config_for_trace()` emits `RunConfig(model_settings=ModelSettings(extra_headers={"x-litellm-spend-logs-metadata": json.dumps({"cadence_trace_id": trace_id})}))`. **Verified live:** over the Responses API the openai-agents SDK uses, LiteLLM persists ONLY the `x-litellm-spend-logs-metadata` header (into `LiteLLM_SpendLogs.metadata->'spend_logs_metadata'`); body `metadata`/`litellm_metadata` and the `x-litellm-trace-id` header are dropped.
- Only the **rebalance / initial-allocation** flow is portfolio-scoped: `ai_portfolio/flows/rebalance.py` wraps the agent call in `llm_trace(str(event_id))` with `session_id` + `event_id` in scope (the session belongs to a portfolio). The recommender (`recommendations/service.py`) and universe-eval (`assets/service.py`) runs are app-global.
- Session KPIs are computed in `paper_trading/service.py::session_kpis` → `SessionKpis` dataclass → `PaperTradingSessionKpisRead` (explicit router mapping) → TS `PaperTradingSessionKpis` → compact KPI tiles on session detail. The `add-daily-avg-cost-kpi` change set the precedent for adding a KPI with no migration.
- Confirmed live on the shared Postgres instance: `LiteLLM_SpendLogs` has `spend` (double precision — authoritative provider-reported cost), `total_tokens` (int), `metadata` (jsonb; our tag nests at `metadata->'spend_logs_metadata'`), `request_tags` (jsonb), `startTime`, `call_type`. The app's `cadence` DB user can read the separate `litellm` database on the same instance.

## Goals / Non-Goals

**Goals:**
- Attribute rebalance/initial-allocation spend to its session + portfolio by enriching the spend-log metadata.
- Surface a cumulative per-session AI cost (USD) KPI tile, sourced from the proxy's authoritative `spend`.
- Keep it opt-in and best-effort: disabled by default, and never able to break `session_kpis` or leak a secret.

**Non-Goals (design-level):**
- Attributing recommender / universe-eval cost to a portfolio (they are global). No per-asset or per-run breakdown, charts, trends, Pushover cost, or dashboard aggregation.
- Duplicating provider pricing app-side — `spend` is authoritative.
- Any write to, or migration of, the `litellm` database; any Cadence migration.

## Decisions

**D1 — Cost source is a read-only second SQLAlchemy engine to the `litellm` database.**
Build a dedicated read-only engine lazily from a new `LITELLM_DATABASE_URL` setting and `SELECT SUM(spend)` from `LiteLLM_SpendLogs` filtered by `metadata->'spend_logs_metadata'->>'cadence_session_id' = <session_id>`. Postgres has no cross-database join, so this is a second connection (same instance, different database) — not a join against the app's session.
*Alternative considered:* the LiteLLM `/spend` HTTP API. Rejected for the read path — it adds an HTTP dependency, needs the proxy process up at KPI-read time, and requires the master key in the app; a direct read-only SQL aggregate is simpler, faster, and independent of the proxy being up.

**D2 — `LITELLM_DATABASE_URL` is independent of `LITELLM_BASE_URL`, default empty = KPI disabled.**
Cost surfacing is a separate opt-in from routing: an operator can route through the proxy without also granting the app DB-read access to the spend log, or vice-versa. Empty URL ⇒ `ai_cost_usd` is `None` and the read is never attempted.

**D3 — The read is best-effort and isolated behind one helper.**
A single helper owns the two LiteLLM-specific couplings (the `LiteLLM_SpendLogs` table name and the `spend_logs_metadata` key), documented with a comment. It returns `None` on an unset URL, a missing table, or any query/connection error — caught and swallowed so `session_kpis` always returns the rest of the KPIs. `ai_cost_usd` is therefore `float | None` end to end (dataclass → read schema → TS `number | null`), and the tile renders `—` for `None`.

**D4 — Attribution generalizes the existing trace seam; the spec delta lives in `ai-paper-trading`, not the gateway.**
Generalize `gateway.py` so the trace context can carry a small metadata mapping (keep `cadence_trace_id`, add `cadence_session_id` and `cadence_portfolio_id`), and thread session/portfolio ids from `flows/rebalance.py`. The gateway code changes, but the *observable behavior* ("a portfolio-scoped run attributes its spend to the session/portfolio") is a paper-trading behavior, so the requirement sits in `ai-paper-trading`. This also sidesteps a fragile cross-change ordering dependency: `add-litellm-model-proxy` (which introduces the `ai-model-gateway` capability) is not yet archived, so its main spec does not exist to MODIFY.
*Alternative considered:* a MODIFIED delta on `ai-model-gateway`. Rejected until that capability's main spec exists (post-archive of the parent change); revisit only if the ordering flips.

**D5 — Cumulative USD cost per session; tokens omitted.**
The KPI is the sum of attributed `spend` to date (cumulative, matching how the proxy records it). Tokens are available but add no decision value for a cost tile and are left out to keep the KPI and tile focused.

**D6 — Secret hygiene for the connection string.**
`LITELLM_DATABASE_URL` carries a password. It is never placed in any read model and never added to the system-status report; any logged/echoed form is redacted (`://user:*****@host`).

## Risks / Trade-offs

- **[Coupling to LiteLLM's schema]** The query depends on the `LiteLLM_SpendLogs` table and the `spend_logs_metadata` key; a LiteLLM upgrade could rename either. → **Mitigation:** isolate both in one helper with a comment, and fail soft (return `None`) so a schema drift degrades the KPI to `—` rather than breaking session detail.
- **[Second DB connection per KPI read]** session_kpis now opens a second engine/connection. → **Mitigation:** build the engine once (module-level lazy singleton) with a small pool; the query is a single indexed-ish aggregate; and it is skipped entirely when the URL is unset.
- **[Attribution gap for in-flight data]** Spend recorded before this change (or by non-portfolio runs) carries no session id and is simply excluded from the sum — the KPI reflects only attributable rebalance spend, which is the intended scope. → No mitigation needed; documented as expected.
- **[Cross-database access assumption]** Relies on the `litellm` DB living on an instance the `cadence` creds can reach. → **Mitigation:** the URL is explicit config; when it cannot connect the read fails soft to `None`.

## Migration Plan

1. Land backend (setting, gateway metadata, rebalance threading, read helper, KPI) and frontend (type + tile) with `LITELLM_DATABASE_URL` empty ⇒ KPI is `—`, no behavior change.
2. Set `LITELLM_DATABASE_URL` for the backend (pointing at the `litellm` database on the shared instance) to light up the KPI. New rebalance runs begin stamping session/portfolio metadata immediately; the KPI reflects spend from runs executed after deploy.
- **Rollback:** unset `LITELLM_DATABASE_URL` ⇒ KPI reverts to `—`; no data migration to undo.

## Open Questions

- None that affect the specs, approach, or task breakdown. (Whether to later also surface tokens or a dashboard-level aggregate is a separate future change, intentionally out of scope.)
