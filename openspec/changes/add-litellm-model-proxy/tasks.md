## 1. Configuration

- [x] 1.1 Add `LITELLM_BASE_URL: str = ""` and `LITELLM_API_KEY: str = ""` to `Settings` in `config.py`, with a docstring noting that an empty base URL disables the proxy (behavior unchanged). Verify: `uv run python -c "from cadence.config import settings; print(settings.LITELLM_BASE_URL, settings.LITELLM_API_KEY)"` prints two empty strings by default.

## 2. Model-provider proxy client seam

- [x] 2.1 Add a startup hook (e.g. in the app/agents bootstrap) that, when `LITELLM_BASE_URL` is set, constructs `AsyncOpenAI(base_url=settings.LITELLM_BASE_URL, api_key=settings.LITELLM_API_KEY)` and registers it via `set_default_openai_client(...)` plus `set_tracing_disabled(True)`; when `LITELLM_BASE_URL` is empty it does nothing. Keep the seam in one chokepoint; do not touch `build_agent`'s signature or the three agents. Verify: a unit test asserts the registration helper is a no-op when `LITELLM_BASE_URL` is empty and calls `set_default_openai_client` exactly once when it is set (patching the SDK functions).
- [x] 2.2 Ensure the hook runs at app startup (and in the agent entrypoints used by the sync-over-async flows) so all three agents pick up the default client when enabled. Verify: with `LITELLM_BASE_URL` set in a test, an agent run (against a fake/stub transport) is issued through the configured client/base URL; with it empty, the SDK's implicit client is used (no client registered).

## 3. Catalog: add Anthropic models

- [x] 3.1 Extend the `AIModel` StrEnum and its display-name map in `paper_trading/constants.py` with Claude entries on LiteLLM's native structured-output allowlist (Sonnet 5.x / Opus 5.x / Haiku 4.5), keeping the existing `gpt-*` entries and default unchanged. Verify: `uv run pytest` for the model-catalog tests passes and the catalog read includes the new Claude ids with display names.
- [x] 3.2 Confirm no migration is required: the `PaperTradingSession.model` column uses `_enum_column(..., native_enum=False)` (stores the value as a string). Verify: adding members does not change DDL — `uv run alembic check` (or the project's equivalent) reports no pending migration attributable to the enum, and a build selecting a Claude id persists and reads back.

## 4. Per-run usage/cost correlation

- [x] 4.1 Pass a trace identifier on each agent run (via the SDK run's request `metadata`/`x-trace-id`) tying the run to its Cadence run id (the `AIPortfolioEvent` id for build/rebalance/close; the recommendation-run id for the recommender; the evaluation-run id for universe-eval). Keep it a no-op-safe addition when the proxy is disabled. Verify: a unit test asserts the trace id is attached to the outgoing run for each agent path; agents still read only `final_output`/tool-call count (no app-side usage extraction added).

## 5. Deployment (proxy as a Compose service on the shared Postgres)

- [x] 5.1 Add a `litellm` service to `docker-compose.yml` (image `ghcr.io/berriai/litellm:main-latest`, `depends_on: db: condition: service_healthy`, port `4000`, a `restart: unless-stopped` policy) that mounts a `config.yaml` and sets `DATABASE_URL=postgresql://cadence:cadence@db:5432/litellm` so its SpendLogs live in the **same `db` Postgres instance** but the **separate `litellm` database**. Set a proxy master key, enable the admin UI (served at `:4000/ui`) with `UI_USERNAME`/`UI_PASSWORD`, and forward `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` + the UI credentials from the root `.env` to the service (proxy-side secrets). Verify: `docker compose up litellm` starts healthy, connects to `db`, and `:4000/ui` loads and authenticates.
- [x] 5.2 Create the separate `litellm` database on the shared instance: add a `CREATE DATABASE litellm;` init script mounted into `db`'s `/docker-entrypoint-initdb.d` (runs on a fresh `pgdata` volume), and document that on an **existing** volume it must be created once manually (`docker compose exec db createdb -U cadence litellm`). (Already created manually on the deployment Pi.) Verify: on a fresh volume the `litellm` database exists after `up`; on an existing volume the documented manual step creates it, and LiteLLM creates its own tables on first start. Confirm the app's Alembic migrations never touch the `litellm` database and LiteLLM never touches `cadence`.
- [x] 5.3 Author the LiteLLM `config.yaml`: a `model_list` mapping each `AIModel` alias → provider model + credential ref (OpenAI for `gpt-*`, Anthropic for `claude-*`), with spend logging enabled (per-request model/tokens/cost persisted to the `litellm` database). Add backend env `LITELLM_BASE_URL=http://litellm:4000` + `LITELLM_API_KEY` (the master/virtual key) to the `backend` service, forwarded from the root `.env`. Verify: a routed request for a `gpt-*` alias reaches OpenAI and a `claude-*` alias reaches Anthropic, and a spend-log row is written with model/tokens/cost in the `litellm` database. (Deployment/ops task; may be performed in the target environment.)

## 6. Live compatibility spike (gating)

- [ ] 6.1 With the proxy + Anthropic key stood up, run a live spike of `output_type` + the `web_search` function tool against a real Claude model through the proxy, confirming the agent reliably emits a schema-valid `final_output` **while** making tool calls. Record the result. If it fails, pause and surface options (restrict Claude to the tool-less universe-eval agent, or a non-strict parse fallback) before offering Claude broadly. Verify: a documented spike run (transcript/log) showing a Claude rebalance/recommender run returning a valid structured result with at least one tool call.

## 7. System-status model-gateway probe

- [x] 7.1 Add a **"Model gateway"** probe to `system/service.py`: a `probe_litellm()` registered in `_PROBES` that, when `LITELLM_BASE_URL` is empty, reports the backend not-configured with no reachability result and makes no network call; when set, probes LiteLLM's unauthenticated `/health/liveliness` endpoint (via a `_check_litellm_liveness` seam) and reports reachable/latency on success or unreachable + a classified, secret-free detail on failure, with the non-secret proxy base URL as the identifier. No schema or frontend change (the status backends list is generic). Verify: service unit tests cover not-configured / reachable / unreachable; the system-status API test lists "Model gateway" among the backends; secret-hygiene test still passes.

## 8. Verification gates

- [x] 8.1 Run `cd backend && uv run ruff check . && uv run mypy src/cadence && uv run pytest` — all green. Frontend only if touched (expected untouched). Verify: all three backend gates pass.
- [x] 8.2 Run `openspec validate --strict` for the change and `openspec validate --specs` — both pass. Verify: commands exit 0.
