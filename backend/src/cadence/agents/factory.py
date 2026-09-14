"""Agent factory wrapping the ``openai-agents`` SDK.

Modeled on the trading-bot ``agent_factory`` but with one hard rule tightened:
``output_type`` is **required**. Every agent this factory builds declares a
Pydantic ``output_type`` so all agent output is a validated model — never
free-text a caller has to parse by hand.
"""

from __future__ import annotations

from typing import Any

from agents.agent import Agent
from pydantic import BaseModel

from cadence.config import settings


def build_agent(
    name: str,
    instructions: str,
    output_type: type[BaseModel],
    tools: list[Any] | None = None,
    model: str | None = None,
) -> Agent:
    """Build an ``openai-agents`` :class:`Agent` with structured output.

    ``output_type`` must be a Pydantic model class; passing anything else (or
    ``None``) is rejected, keeping structured output non-optional. The model id
    defaults to :data:`settings.RECOMMENDER_MODEL`; callers wanting a different
    model (e.g. the AI portfolio manager on ``AI_PORTFOLIO_MODEL``) pass ``model``
    explicitly.
    """
    if not (isinstance(output_type, type) and issubclass(output_type, BaseModel)):
        raise TypeError(
            "build_agent requires a Pydantic model class as output_type; "
            "agents must always produce structured output."
        )

    return Agent(
        name=name,
        instructions=instructions,
        model=model or settings.RECOMMENDER_MODEL,
        tools=tools or [],
        output_type=output_type,
    )
