"""Unit tests for the orchestrator agent's prompt and wiring (no network)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from tests.fakes import FakeOrchestratorAgent

from cadence.agents.tools import web_search
from cadence.bot_orchestrator import agent as agent_module
from cadence.bot_orchestrator.agent import (
    ORCHESTRATOR_PROMPT_VERSION,
    OpenAIOrchestratorAgent,
    OrchestratorAgent,
    OrchestratorDecision,
    RunUsage,
    build_orchestrator_prompt,
    usage_from_sdk,
)
from cadence.bot_orchestrator.errors import OrchestratorUnavailableError


def _briefing() -> dict[str, Any]:
    return {
        "as_of": "2026-11-10T14:00:00+00:00",
        "limits": {"free_capital": 7000.0, "open_slots": 2, "max_bot_capital": 5000.0},
        "market": [{"index": "S&P 500", "status": "available", "rsi_14": 58.1}],
        "sectors": {
            "breadth": [{"sector": "technology", "gate_pass_share": 0.6}],
            "news_tone": {"status": "unavailable"},
        },
        "strategies": [
            {"key": "donchian_breakout", "style": "breakout", "explanation": "Buys new highs."}
        ],
        "presets": [{"key": "donchian_turtle_algo25", "name": "Turtle Breakout"}],
        "running_bots": [{"bot_id": "b-1", "preset_key": "ma_crossover_algo6"}],
        "liquidating_bots": [],
        "candidates": [{"ticker": "AAPL", "sector": "technology"}],
    }


def test_prompt_includes_every_section() -> None:
    prompt = build_orchestrator_prompt(_briefing())

    for heading in (
        "## Limits",
        "## Market technicals (indices)",
        "## Sector breadth",
        "## Sector news tone",
        "## Strategies",
        "## Presets",
        "## Running bots",
        "## Candidate tickers",
    ):
        assert heading in prompt
    assert '"free_capital":7000.0' in prompt
    assert "donchian_turtle_algo25" in prompt
    assert '"bot_id":"b-1"' in prompt
    assert ORCHESTRATOR_PROMPT_VERSION >= 3
    assert '"style":"breakout"' in prompt
    assert prompt.index("## Strategies") < prompt.index("## Presets")


def test_instructions_match_presets_by_style() -> None:
    from cadence.bot_orchestrator.agent import _AGENT_INSTRUCTIONS

    for phrase in ("Strategies section", "mean-reversion", "regime-switching", "momentum"):
        assert phrase in _AGENT_INSTRUCTIONS


def test_instructions_carry_recent_developments_guidance() -> None:
    from cadence.bot_orchestrator.agent import _AGENT_INSTRUCTIONS

    for phrase in ("last 7 days", "top_stories", "fiscal years", "month and year"):
        assert phrase in _AGENT_INSTRUCTIONS


def test_prompt_is_deterministic() -> None:
    assert build_orchestrator_prompt(_briefing()) == build_orchestrator_prompt(
        _briefing()
    )


def test_agent_is_built_with_output_type_and_web_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_build_agent(**kwargs: Any) -> object:
        captured.update(kwargs)
        raise RuntimeError("stop before running")

    monkeypatch.setattr(agent_module, "build_agent", fake_build_agent)

    with pytest.raises(RuntimeError):
        OpenAIOrchestratorAgent().decide(_briefing(), model="gpt-5-mini")

    assert captured["output_type"] is OrchestratorDecision
    assert captured["tools"] == [web_search]
    assert captured["model"] == "gpt-5-mini"


def test_timeout_raises_domain_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _NeverFinishes:
        @staticmethod
        async def run(*args: object, **kwargs: object) -> object:
            await asyncio.sleep(1)
            raise AssertionError("should have timed out")  # pragma: no cover

    monkeypatch.setattr(agent_module, "Runner", _NeverFinishes)
    monkeypatch.setattr(agent_module.settings, "BOT_ORCHESTRATOR_TIMEOUT_SECONDS", 0)

    with pytest.raises(OrchestratorUnavailableError) as excinfo:
        OpenAIOrchestratorAgent().decide(_briefing(), model="gpt-5-mini")

    assert "timed out" in str(excinfo.value)


def test_fake_agent_satisfies_the_protocol() -> None:
    fake = FakeOrchestratorAgent()

    assert isinstance(fake, OrchestratorAgent)
    result = fake.decide(_briefing(), model="m")
    assert result.decision.stops == [] and result.decision.deploys == []
    assert result.usage == FakeOrchestratorAgent.USAGE
    assert fake.calls[0][1] == "m"


def test_production_agent_returns_sdk_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    decision = OrchestratorDecision(market_summary="Quiet.")

    class _Usage:
        requests = 3
        input_tokens = 2_000
        output_tokens = 150
        total_tokens = 2_150

    class _Context:
        usage = _Usage()

    class _Result:
        final_output = decision
        context_wrapper = _Context()

    class _Runner:
        @staticmethod
        async def run(*args: object, **kwargs: object) -> _Result:
            return _Result()

    monkeypatch.setattr(agent_module, "Runner", _Runner)

    result = OpenAIOrchestratorAgent().decide(_briefing(), model="gpt-5-mini")

    assert result.decision is decision
    assert result.usage == RunUsage(
        requests=3, input_tokens=2_000, output_tokens=150, total_tokens=2_150
    )
    assert result.usage.as_dict()["total_tokens"] == 2_150


def test_usage_from_sdk_handles_missing_usage() -> None:
    assert usage_from_sdk(None) is None
