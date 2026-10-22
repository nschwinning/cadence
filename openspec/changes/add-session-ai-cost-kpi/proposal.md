## Why

Routing agent runs through the LiteLLM proxy (`add-litellm-model-proxy`) now captures authoritative per-request token/cost figures in the proxy's spend log, but that cost is invisible inside Cadence and is not attributed to anything. Operators want to know **what the AI is costing them per paper-trading session/portfolio** — the rebalance/initial-allocation runs are already portfolio-scoped, so their spend can be attributed and surfaced as a per-session KPI alongside the existing performance tiles.

## What Changes

- **Attribute portfolio-scoped LLM spend.** Generalize the gateway trace seam so a rebalance / initial-allocation run stamps structured metadata — the session id and portfolio id (keeping the existing trace id) — into the LiteLLM spend-log row's `spend_logs_metadata`. Recommender and universe-evaluation runs are app-global, not portfolio-scoped, so they remain **unattributed** (explicit non-goal).
- **Add a per-session AI-cost read path.** A best-effort, **read-only** aggregation of the proxy's authoritative `spend` for a session, summed from the LiteLLM spend log filtered by the stamped session id. Sourced via a separate read-only connection to the `litellm` database (same Postgres instance as the app DB).
- **Surface a new `AI cost` KPI tile.** Thread a cumulative-per-session `ai_cost_usd` value through the session KPIs into a new KPI tile on the session-detail Performance group, mirroring the existing compact KPI pattern.
- **New configuration:** `LITELLM_DATABASE_URL` (default empty). Empty ⇒ the cost KPI is disabled and reports no value (independent of whether LLM routing itself is enabled). The read is **best-effort**: an unset URL, an absent table, or a query error yields no cost (the tile renders `—`) and never breaks the rest of the session KPIs.
- **No migration.** The KPI is a read-only aggregation of an external (LiteLLM-owned) table; no Cadence schema change.

## Capabilities

### New Capabilities
<!-- None — this change extends existing capabilities. -->

### Modified Capabilities
- `ai-paper-trading`: add a requirement for the per-session AI-cost KPI — portfolio-scoped (rebalance/initial-allocation) runs attribute their spend to the session/portfolio, and the session KPIs expose a cumulative USD AI cost that is best-effort and absent when the cost source is unconfigured.
- `app-shell`: the session-detail performance KPI tiles gain an `AI cost` tile that renders the per-session cost (and `—` when unavailable).

## Impact

- **Backend code:** `config.py` (new `LITELLM_DATABASE_URL`); `agents/gateway.py` (richer trace metadata — session/portfolio id, not just the trace id); `ai_portfolio/flows/rebalance.py` (pass session/portfolio id into the trace); a new read-only LiteLLM-spend helper + a dedicated lazily-built read-only engine; `paper_trading/service.py::session_kpis` + the `SessionKpis` dataclass; `api/schemas.py` (`PaperTradingSessionKpisRead`) + the explicit router mapping.
- **Frontend code:** `types/api.ts` (`PaperTradingSessionKpis` gains `ai_cost_usd`); the session-detail Performance KPI group gains one tile.
- **Data / deployment:** reads (never writes) the LiteLLM-owned `LiteLLM_SpendLogs` table in the `litellm` database; `LITELLM_DATABASE_URL` is a new deployment env var (a connection string — treated as a secret, never surfaced in any read model or the system-status report).
- **Depends on** `add-litellm-model-proxy` (the gateway seam + spend logging) being deployed; builds on its verified `x-litellm-spend-logs-metadata` correlation mechanism.
- **Out of scope:** attributing recommender/universe-evaluation cost to a portfolio; per-asset or per-run cost breakdowns; cost charts/trends; cost in the daily P&L Pushover; dashboard-level aggregate cost across portfolios; any write to or migration of the `litellm` database; changing LLM routing or when agents run.
