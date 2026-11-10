## Why

Today every AI agent run is locked to OpenAI: the `openai-agents` SDK builds its own implicit client from `OPENAI_API_KEY`, and the codebase never constructs a client or sets a `base_url`, so there is no seam to route a run to another provider. We want to be able to run a session on Anthropic (Claude) models as well, and we have no visibility into token usage or cost per run. Routing all agent LLM calls through a LiteLLM proxy gives us both — multi-provider routing (OpenAI + Anthropic) by model string, and centralized per-request token/cost accounting — without touching how agents are written or invoked.

## What Changes

- Add an **opt-in LLM gateway seam**: when a proxy base URL is configured, construct a single `AsyncOpenAI(base_url=…, api_key=…)` and register it as the default client for the `openai-agents` SDK (and disable OpenAI-platform tracing) at app startup. The app keeps selecting models by **model string**; the LiteLLM proxy routes `gpt-*` → OpenAI and `claude-*` → Anthropic.
- **Disabled by default:** when no proxy base URL is set, behavior is byte-for-byte unchanged (the SDK's implicit OpenAI client), so existing deployments, offline stubs, and tests are unaffected.
- Extend the **AI model catalog** (`AIModel`) with recent Claude entries (on LiteLLM's native structured-output path — Claude Sonnet 5.x / Opus 5.x / Haiku 4.5) alongside the existing `gpt-*` models. These model strings become the aliases the proxy maps to providers. (This adds catalog entries only; the existing "AI model catalog" requirement's spec'd behavior is unchanged, so no `ai-paper-trading` requirement changes.)
- **Capture token usage and cost per run** via the proxy's spend log (per-request model/tokens/cost), correlated back to a Cadence run through a trace identifier passed on each agent call. Usage/cost lives in the proxy's own store; Cadence does not thread usage extraction through the three agents.
- New configuration: a proxy base URL (default empty = disabled) and a proxy API key. The Anthropic key is held by the **proxy**, not the app.
- Deployment: a LiteLLM proxy service plus its model-alias → provider mapping, with spend logging enabled.
- Add a **"Model gateway" backend to the System status report** so an operator can confirm the proxy is connected after redeploy. The probe hits the gateway's unauthenticated liveness endpoint; it is opt-in like the rest of this change — when no proxy base URL is configured the gateway is reported not-configured and is never probed. No schema or frontend change (the status backends list is already generic).
- **Scope deliberately excludes DeepSeek and other providers:** DeepSeek cannot serve schema-enforced `json_schema` structured outputs, which would collide with the agent factory's mandatory Pydantic `output_type` contract. OpenAI and Anthropic both support native structured outputs, so that contract stays intact.

## Capabilities

### New Capabilities
- `ai-model-gateway`: how the system routes agent LLM calls to a model provider (OpenAI or Anthropic) through an optional, disabled-by-default proxy selected by model string, and how it captures per-run token usage and cost.

### Modified Capabilities
- `system-status`: the backend-status report gains a "Model gateway" backend — the optional LiteLLM proxy, probed via its unauthenticated liveness endpoint, reported not-configured (and never probed) when the proxy base URL is unset.
<!-- Adding Claude entries to the model catalog is an additive catalog change that does not alter the existing "AI model catalog" requirement's behavior, so no `ai-paper-trading` delta. -->

## Impact

- **Code:** `config.py` (new proxy settings); an app-startup hook / `agents/factory.py` seam (`set_default_openai_client` + `set_tracing_disabled`, gated on the proxy being configured); `paper_trading/constants.py` (`AIModel` catalog + display map); a trace-id passed on each `Runner.run` call. No migration (the `model` column is a non-native string enum, so new members need no schema change).
- **Agents:** the three `*Agent` Protocol seams, their OpenAI implementations, and the offline stubs are unchanged and remain a no-op path when the proxy is disabled.
- **Deployment:** a new LiteLLM proxy service + its config (model-alias → provider mapping, spend logging to a store). The Anthropic API key is a proxy-side secret.
- **System status:** `system/service.py` gains a `probe_litellm` backend probe in the `_PROBES` registry (opt-in, liveness-only, not-configured when disabled). No read-schema or frontend change — the backends list is generic.
- **Dependencies:** no new backend Python dependency required for the disabled-by-default path (the SDK already speaks the OpenAI client); the proxy is an external service.
- **Out of scope:** DeepSeek/other providers; streaming usage; changing the mandatory `output_type` contract; surfacing usage/cost in the UI; removing the dead-code build path; any change to when/how agents run or to prompts.
