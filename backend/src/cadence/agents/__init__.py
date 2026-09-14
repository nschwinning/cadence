"""Reusable AI-agent building blocks.

A thin, provider-agnostic wrapper over the ``openai-agents`` SDK. The
:func:`build_agent` factory is deliberately generic so it can back any future
agent, not just the asset recommender. Every agent it produces is forced to
return a Pydantic model — free-text output parsed by hand is not allowed.
"""

from cadence.agents.factory import build_agent

__all__ = ["build_agent"]
