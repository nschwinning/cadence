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
import json
from collections.abc import Iterator, Mapping

from agents import ModelSettings, RunConfig, set_default_openai_client, set_tracing_disabled
from openai import AsyncOpenAI

from cadence.config import settings

# Per-run spend-log metadata, set by the caller that knows the Cadence run and
# (for portfolio-scoped runs) the session/portfolio it belongs to, and read at
# each ``Runner.run`` boundary so the proxy's usage record can be joined back to
# the originating run — and attributed to a session for cost reporting. ``None``
# when nothing set it. Always carries ``cadence_trace_id``; portfolio-scoped
# runs additionally carry ``cadence_session_id`` + ``cadence_portfolio_id``.
_trace_metadata: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "cadence_llm_trace_metadata", default=None
)

# LiteLLM request header carrying a JSON object to persist on the proxy's
# spend-log row (its ``spend_logs_metadata`` column). Verified empirically to be
# the only mechanism LiteLLM records for runs issued over the Responses API: the
# Responses ``metadata`` param and a bare ``x-litellm-trace-id`` header are both
# dropped, so this header is how a usage row is joined back to a Cadence run.
_SPEND_LOG_METADATA_HEADER = "x-litellm-spend-logs-metadata"

# Key under which the Cadence run id is stored inside that JSON object.
_TRACE_METADATA_KEY = "cadence_trace_id"
# Keys that attribute a portfolio-scoped run's spend to its session/portfolio.
_SESSION_METADATA_KEY = "cadence_session_id"
_PORTFOLIO_METADATA_KEY = "cadence_portfolio_id"


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
def llm_trace(
    trace_id: str | None,
    *,
    session_id: str | None = None,
    portfolio_id: str | None = None,
) -> Iterator[None]:
    """Tag agent runs started within this block with spend-log metadata.

    ``trace_id`` correlates captured usage back to the Cadence run. For
    portfolio-scoped runs (rebalance / initial allocation), pass ``session_id``
    and ``portfolio_id`` so the proxy's spend can be attributed to that session
    for cost reporting; the global recommender/universe-eval runs pass neither.
    The metadata rides along on each ``Runner.run`` via
    :func:`run_config_for_trace`. A no-op when the gateway is disabled.
    """
    metadata: dict[str, str] | None
    if not trace_id:
        metadata = None
    else:
        metadata = {_TRACE_METADATA_KEY: trace_id}
        if session_id:
            metadata[_SESSION_METADATA_KEY] = session_id
        if portfolio_id:
            metadata[_PORTFOLIO_METADATA_KEY] = portfolio_id
    token = _trace_metadata.set(metadata)
    try:
        yield
    finally:
        _trace_metadata.reset(token)


def run_config_for_trace() -> RunConfig | None:
    """Build a per-run ``RunConfig`` carrying the current spend-log metadata.

    Returns ``None`` when the gateway is disabled or no trace is set, so callers
    pass ``run_config=None`` and SDK behavior is unchanged.
    """
    if not gateway_enabled():
        return None
    metadata: Mapping[str, str] | None = _trace_metadata.get()
    if not metadata:
        return None
    return RunConfig(
        model_settings=ModelSettings(
            extra_headers={
                _SPEND_LOG_METADATA_HEADER: json.dumps(dict(metadata)),
            },
        )
    )
