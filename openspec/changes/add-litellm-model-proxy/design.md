## Context

See proposal.md — Why. Relevant current state that shapes the approach:

- Every agent is built by `agents/factory.py::build_agent(...)`, which hands the `openai-agents` SDK a **model string only**. The SDK constructs its own implicit global client from `OPENAI_API_KEY`; the codebase never builds a client, sets a `base_url`, or calls `set_default_openai_client`/`set_tracing_disabled`. So there is **no existing seam** to redirect runs to another provider — this change adds exactly that one seam.
- Three agents go through the factory: AI-portfolio rebalance (`ai_portfolio/agent.py`, `tools=[web_search]`, `model=session.model`), recommender (`recommendations/agent.py`, `tools=[web_search]`, defaults to `RECOMMENDER_MODEL`), and universe-eval (`assets/universe_agent.py`, tool-less, `RECOMMENDER_MODEL`). Each sits behind a Protocol + OpenAI impl + offline stub at the service boundary.
- `web_search` is a custom `@function_tool` (`agents/tools.py`), **not** OpenAI's hosted `WebSearchTool`, so it is ordinary tool-calling that LiteLLM maps to Anthropic natively.
- `build_agent` **requires** a Pydantic `output_type` (schema-enforced structured output). The live output models (`AIRebalanceResult`/`AITargetAllocation`, `RecommendationOutput`/`RecommendationCandidate`, `UniverseEvaluationOutput`) are flat objects — no discriminated unions/`oneOf`, no enums (the only enum lives in the dead-code build path) — so they pass OpenAI strict mode and Anthropic native structured output without a schema refactor.
- The `AIModel` catalog (`paper_trading/constants.py`) is selected per build and frozen on `PaperTradingSession.model`. That column uses `_enum_column(..., native_enum=False)` — it stores the member **value as a string**, so adding catalog members needs **no migration**.
- No token usage/cost is captured today; only `final_output` and a tool-call count are read off a `RunResult`.

## Goals / Non-Goals

**Goals:**
- Add a single opt-in client seam that, when a proxy is configured, routes all three agents' runs through the LiteLLM proxy by model string.
- Keep the disabled path byte-for-byte identical to today (no proxy configured → SDK's implicit OpenAI client), so existing deploys, stubs, and tests are untouched.
- Offer Anthropic (Claude) models in the catalog alongside OpenAI models.
- Capture per-run token usage/cost in the proxy's store, correlated to the Cadence run by a trace id, without threading usage extraction through the agents.

**Non-Goals (design-level):**
- No provider beyond OpenAI/Anthropic; no DeepSeek.
- No change to `build_agent`'s mandatory `output_type`.
- No app-side usage/cost columns or UI surfacing in this change (proxy store is the source of truth; app-side persistence is a possible follow-up).
- No per-agent client wiring — the seam is global, set once.

## Decisions

**D1 — Global default client via `set_default_openai_client`, not per-`build_agent` `LitellmModel`.**
Construct one `AsyncOpenAI(base_url=LITELLM_BASE_URL, api_key=LITELLM_API_KEY)` and register it with `set_default_openai_client(...)` (+ `set_tracing_disabled(True)`, since we are not using the OpenAI platform) at app startup, gated on `LITELLM_BASE_URL` being set. Agents keep passing model strings; the proxy routes by alias.
*Alternative considered:* the `LitellmModel` SDK extension per agent. Rejected — it moves provider logic into app code, must be threaded through every `build_agent` call site, and loses the centralized spend store unless the proxy runs anyway. The global-client seam is one chokepoint and keeps `build_agent` unchanged.

**D2 — Opt-in, disabled by default.**
When `LITELLM_BASE_URL` is empty the startup hook does nothing and the SDK falls back to its implicit `OPENAI_API_KEY` client — identical to today. This keeps the offline stubs, the `RECOMMENDER_STUB` path, and all existing tests unaffected, and makes rollout a config flip.

**D3 — Catalog expansion is code-only.**
Add Claude members to `AIModel` (+ display-name map). These strings are the proxy aliases. Because `model` is a non-native string enum column, no migration. Choose Claude models on LiteLLM's **native structured-output allowlist** (Sonnet 5.x / Opus 5.x / Haiku 4.5) so structured output uses the native path, not tool-emulation.
*Note:* the existing "AI model catalog" requirement in `ai-paper-trading` is generic ("a fixed, server-defined catalog"); adding entries does not change its spec'd behavior, so no delta there. The new provider-aware offering is captured in `ai-model-gateway`.

**D4 — Usage/cost lives in the proxy store, correlated by trace id.**
Enable LiteLLM spend logging (per-request model/tokens/cost) to its store. Pass a trace identifier on each run (via request `metadata`/`x-trace-id`, e.g. the `AIPortfolioEvent` id or recommendation-run id) so a proxy usage row can be joined back to the Cadence run. We do **not** read usage off `RunResult` in the three agents.
*Alternative considered:* extract `usage` from each `RunResult` and persist app-side on the per-run row (`AIPortfolioEvent` already has `model`/`duration_ms`). Deferred — it means touching all three agents and a schema/`run_stats` change for marginal gain while the proxy already records authoritative, provider-reported figures. Kept as an optional follow-up.

**D5 — Keep the OpenAI-direct probe AND add a dedicated model-gateway probe.**
`system/service.py::_build_openai_client` keeps probing OpenAI directly (that probe validates the OpenAI backend itself, independent of routing). Additionally, add a new **"Model gateway"** backend probe to the existing system-status registry so the status tab shows the proxy as connected once it is deployed and `LITELLM_BASE_URL` is set. The probe hits LiteLLM's **unauthenticated** `/health/liveliness` endpoint — no proxy credential is sent, so it proves only that the gateway process is up and reachable. The gateway is opt-in like the rest of this change: when `LITELLM_BASE_URL` is empty the probe reports the backend **not configured** with no reachability result (never a spurious "down"), mirroring the disabled-by-default routing. This needs no schema or frontend change — `SystemStatusRead.backends` is a generic list already rendered per-backend; only `system/service.py` (new `probe_litellm` added to `_PROBES`) and its tests change.
*Why include it now (reversing the earlier deferral):* the operator's verification path for this change is the System status tab showing the gateway connected after redeploy, so the probe is in-scope rather than a later change. It expands the change's footprint into the `system-status` capability — see the spec delta.

**D6 — LiteLLM runs as a Compose service, reusing the existing Postgres instance on a separate database.**
Add a `litellm` service to `docker-compose.yml` (image `ghcr.io/berriai/litellm:main-latest`, `depends_on: db: service_healthy`), mounting a `config.yaml` and configured with a proxy master key and `DATABASE_URL=postgresql://cadence:cadence@db:5432/litellm` so its SpendLogs tables live in the **same Postgres instance** (`db`) but a **separate `litellm` database**, isolated from the app's `cadence` schema. The backend reaches it over the compose network at `LITELLM_BASE_URL=http://litellm:4000`. The proxy owns the OpenAI and Anthropic keys (forwarded from the root `.env`); the backend only holds `LITELLM_BASE_URL` + `LITELLM_API_KEY`. The **LiteLLM admin UI** is enabled (served at `:4000/ui`, backed by the `litellm` database) with admin credentials (`UI_USERNAME`/`UI_PASSWORD`) forwarded from the root `.env`, so usage/cost can be browsed without SQL.
*Creating the second database:* Postgres' `POSTGRES_DB` creates only the one `cadence` database, and `/docker-entrypoint-initdb.d` scripts run **only when the data volume is first initialized**. So:
- **Fresh installs:** add an init script (`CREATE DATABASE litellm;`) mounted into `db`'s `/docker-entrypoint-initdb.d`, which runs on first volume init.
- **Existing `pgdata` volumes:** the init script will NOT re-run, so the `litellm` database must be created once manually (`docker compose exec db createdb -U cadence litellm`, or `CREATE DATABASE litellm;` via psql). LiteLLM creates its own tables (Prisma migrations) on first start.
LiteLLM manages its own schema in the `litellm` database; Alembic/the app never touch it, and the app's own migrations never touch `litellm`.
*Alternative considered:* a dedicated second Postgres container for LiteLLM. Rejected per the user's preference to reuse the one instance — a separate database gives schema isolation without a second server, volume, and healthcheck.

## Risks / Trade-offs

- **[Structured output + tools on Claude may misbehave]** The rebalance and recommender agents combine mandatory `output_type` with the `web_search` function tool — the same combination that breaks structured output on some non-OpenAI providers. Static analysis is favorable (custom function tool, flat schemas, Claude on the native allowlist) but cannot prove runtime behavior. → **Mitigation:** an explicit live spike task before wider rollout — run output_type + web_search against a real Claude model through the proxy and confirm the agent emits a schema-valid `final_output` while making tool calls. If it fails, the fallback is to restrict Claude to the tool-less universe-eval agent initially, or add a non-strict parse path (a larger follow-up), and that finding gates how broadly Claude is offered.
- **[LiteLLM Anthropic native-output allowlist is model-name gated]** A model off LiteLLM's hardcoded allowlist silently falls back to tool-emulation (and a known bug can leak the tool envelope). → **Mitigation:** pick catalog Claude identifiers known to be on the native allowlist; the spike validates the exact strings.
- **[New external dependency: the proxy service]** A misconfigured or down proxy would fail agent runs when enabled. → **Mitigation:** opt-in/disabled-by-default means the proxy is only in the path once deliberately configured; the disabled path has zero new failure modes. Agent runs already run under bounded timeouts.
- **[Secrets topology changes]** The Anthropic key moves to a proxy-side secret, and a proxy API key is added to the app. → **Mitigation:** app holds only `LITELLM_BASE_URL` + `LITELLM_API_KEY`; the Anthropic key never enters the app config. Existing "never expose secrets in status" behavior is unaffected.

## Migration Plan

1. Land code (settings, startup seam, catalog, trace id) with `LITELLM_BASE_URL` empty → no behavioral change; ships dark.
2. Add the `litellm` Compose service + its `config.yaml` (model-alias → provider mapping, SpendLogs enabled) pointing `DATABASE_URL` at `db:5432/litellm`; add the `CREATE DATABASE litellm` init script for fresh installs and create the `litellm` database manually on any existing `pgdata` volume. Hold OpenAI/Anthropic keys proxy-side.
3. Run the live structured-output + web_search spike against a Claude model through the proxy.
4. Flip `LITELLM_BASE_URL=http://litellm:4000` + `LITELLM_API_KEY` for the backend to route through the proxy.
- **Rollback:** unset `LITELLM_BASE_URL` → instantly reverts to the implicit OpenAI client; no data migration to undo. The `litellm` database is independent and can be left in place or dropped.

## Open Questions

- Which exact Claude identifiers to seat in the catalog first (Sonnet vs Haiku) — resolved by the spike; does not change the specs, approach, or task breakdown.
- Whether to later persist a compact usage summary app-side on the per-run row for in-product display — a separate follow-up change, intentionally out of scope.
