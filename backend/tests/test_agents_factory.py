"""Unit tests for the reusable agent factory.

These construct an agent in-process only; no network calls are made (building an
:class:`Agent` does not contact the model).
"""

from __future__ import annotations

import pytest
from agents.agent import Agent
from pydantic import BaseModel

from cadence.agents import build_agent
from cadence.agents.tools import web_search


class _Output(BaseModel):
    value: str


def test_build_agent_constructs_agent_with_structured_output() -> None:
    agent = build_agent(
        name="TestAgent",
        instructions="Do something.",
        output_type=_Output,
        tools=[web_search],
    )

    assert isinstance(agent, Agent)
    assert agent.output_type is _Output
    assert web_search in agent.tools


def test_build_agent_rejects_missing_output_type() -> None:
    with pytest.raises(TypeError):
        build_agent(
            name="TestAgent",
            instructions="Do something.",
            output_type=None,  # type: ignore[arg-type]
        )


def test_build_agent_rejects_non_pydantic_output_type() -> None:
    with pytest.raises(TypeError):
        build_agent(
            name="TestAgent",
            instructions="Do something.",
            output_type=dict,  # type: ignore[arg-type]
        )
