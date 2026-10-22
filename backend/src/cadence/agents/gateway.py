"""Opt-in LiteLLM model-gateway seam for the ``openai-agents`` SDK.

The SDK normally builds its own implicit OpenAI client from ``OPENAI_API_KEY``;
there is no other seam to redirect a run to a different provider. When
``LITELLM_BASE_URL`` is configured this module registers a single
``AsyncOpenAI`` client pointed at that OpenAI-compatible proxy as the SDK's
default client (and disables OpenAI-platform tracing, since we are no longer
talking to the OpenAI platform directly). The proxy then routes each run to its
provider by model string (``gpt-*`` → OpenAI, ``claude-*`` → Anthropic) and
records per-request token usage/cost.

Everything here is a **no-op when the gateway is disabled** (empty
``LITELLM_BASE_URL``): the SDK keeps its implicit OpenAI client and behavior —
including the offline stubs and the test suite — is byte-for-byte unchanged.
"""

from __future__ import annotations

import contextlib
import contextvars
from collections.abc import Iterator

from agents import ModelSettings, RunConfig, set_default_openai_client, set_tracing_disabled
from openai import AsyncOpenAI

from cadence.config import settings

# Per-run trace identifier, set by the caller that knows the Cadence run id
# (the AIPortfolioEvent id, the recommendation-run id, or the evaluation-run id)
# and read at each ``Runner.run`` boundary so the proxy's usage record can be
# joined back to the originating run. ``None`` when nothing set it.
_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "cadence_llm_trace_id", default=None
)


def gateway_enabled() -> bool:
    """Return True when a proxy endpoint is configured (gateway active)."""
    return bool(settings.LITELLM_BASE_URL.strip())


def configure_model_gateway() -> bool:
    """Register the proxy as the SDK's default client when configured.

    Safe to call once at startup. Returns True if the gateway was configured
    (the proxy is now in the path for every agent run), False when it is
    disabled and the SDK keeps its implicit OpenAI client.
    """
    if not gateway_enabled():
        return False
    client = AsyncOpenAI(
        base_url=settings.LITELLM_BASE_URL.strip(),
        # The proxy's master/virtual key. A placeholder keeps client
        # construction from raising when only the base URL is set; the proxy
        # itself rejects an invalid key at call time with a clear 401.
        api_key=settings.LITELLM_API_KEY or "sk-litellm-proxy",
    )
    set_default_openai_client(client)
    set_tracing_disabled(True)
    return True


@contextlib.contextmanager
def llm_trace(trace_id: str | None) -> Iterator[None]:
    """Tag agent runs started within this block with ``trace_id``.

    The id rides along on each ``Runner.run`` via :func:`run_config_for_trace`
    so the proxy can correlate captured usage back to the Cadence run. A no-op
    when the gateway is disabled.
    """
    token = _trace_id.set(trace_id)
    try:
        yield
    finally:
        _trace_id.reset(token)


def run_config_for_trace() -> RunConfig | None:
    """Build a per-run ``RunConfig`` carrying the current trace id for the proxy.

    Returns ``None`` when the gateway is disabled or no trace id is set, so
    callers pass ``run_config=None`` and SDK behavior is unchanged.
    """
    if not gateway_enabled():
        return None
    trace_id = _trace_id.get()
    if not trace_id:
        return None
    return RunConfig(
        model_settings=ModelSettings(
            metadata={"cadence_trace_id": trace_id},
            extra_headers={"x-litellm-trace-id": trace_id},
        )
    )
