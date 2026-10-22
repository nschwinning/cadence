"""Reusable AI-agent building blocks.

A thin, provider-agnostic wrapper over the ``openai-agents`` SDK. The
:func:`build_agent` factory is deliberately generic so it can back any future
agent, not just the asset recommender. Every agent it produces is forced to
return a Pydantic model — free-text output parsed by hand is not allowed.
"""

from cadence.agents.factory import build_agent
from cadence.agents.gateway import (
    configure_model_gateway,
    gateway_enabled,
    llm_trace,
    run_config_for_trace,
)

__all__ = [
    "build_agent",
    "configure_model_gateway",
    "gateway_enabled",
    "llm_trace",
    "run_config_for_trace",
]
