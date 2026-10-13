"""Unit tests for the universe-evaluation agent's prompt and output wiring.

No network calls: these exercise the prompt builder and confirm the agent is
constructed with the Pydantic ``output_type`` and surfaces timeouts as the
domain error.
"""

from __future__ import annotations

import asyncio

import pytest

from cadence.agents import build_agent
from cadence.assets import universe_agent as agent_module
from cadence.assets.errors import AssetEvaluationUnavailableError
from cadence.assets.universe_agent import (
    OpenAIUniverseEvaluationAgent,
    RosterEntry,
    UniverseEvaluationOutput,
    UniverseSummary,
    build_universe_evaluation_prompt,
)


def _summary() -> UniverseSummary:
    return UniverseSummary(
        total=5,
        eligible_count=4,
        ineligible_count=1,
        category_counts={"stock": 4, "crypto": 1},
        sector_counts={"technology": 3, "energy": 1, "none": 1},
        top_concentrations=[("technology", 3), ("energy", 1)],
        unpriceable_listings=["AIR.PA", "TTE.PA"],
        sector_roster=(
            (
                "technology",
                (
                    RosterEntry("AAPL", "Apple Inc.", True),
                    RosterEntry("MSFT", "Microsoft Corp.", True),
                    RosterEntry("NVDA", "NVIDIA Corp.", False),
                ),
            ),
            ("energy", (RosterEntry("XOM", "Exxon Mobil Corp.", True),)),
            ("Crypto", (RosterEntry("BTC-USD", "Bitcoin", True),)),
        ),
    )


def test_prompt_includes_totals_composition_and_listings() -> None:
    prompt = build_universe_evaluation_prompt(_summary())

    assert "5 assets" in prompt
    assert "4 eligible" in prompt
    assert "1 ineligible" in prompt
    # Category and sector composition rendered largest-first.
    assert "stock 4" in prompt
    assert "technology 3" in prompt
    assert "none 1" in prompt
    # Foreign/unpriceable listings surfaced by ticker.
    assert "AIR.PA" in prompt
    assert "TTE.PA" in prompt
    # No numeric scoring is requested.
    assert "numeric scores" in prompt


def test_prompt_states_cadence_trading_scope() -> None:
    prompt = build_universe_evaluation_prompt(_summary()).lower()

    # Scope: US-tradable individual stocks + crypto, long-only.
    assert "stocks and crypto" in prompt
    assert "long-only" in prompt
    # Unsupported instrument classes are called out as out of scope.
    assert "etf" in prompt
    assert "fixed-income" in prompt
    # Suggestions must not recommend the unsupported classes.
    assert "do not recommend" in prompt


def test_prompt_handles_empty_listings() -> None:
    summary = UniverseSummary(
        total=2,
        eligible_count=2,
        ineligible_count=0,
        category_counts={"stock": 2},
        sector_counts={"technology": 2},
        top_concentrations=[("technology", 2)],
        unpriceable_listings=[],
        sector_roster=(
            (
                "technology",
                (
                    RosterEntry("AAPL", "Apple Inc.", True),
                    RosterEntry("MSFT", "Microsoft Corp.", True),
                ),
            ),
        ),
    )
    prompt = build_universe_evaluation_prompt(summary)

    assert "Foreign/unpriceable listings: none" in prompt


def test_prompt_lists_roster_and_forbids_duplicate_suggestions() -> None:
    prompt = build_universe_evaluation_prompt(_summary())

    # The roster block names each holding as "TICKER — Name" under its sector.
    assert "Assets already in the universe (grouped by sector)" in prompt
    assert "technology (3):" in prompt
    assert "AAPL — Apple Inc." in prompt
    assert "XOM — Exxon Mobil Corp." in prompt
    # Crypto grouped under its own heading.
    assert "Crypto (1):" in prompt
    assert "BTC-USD — Bitcoin" in prompt
    # Ineligible holdings flagged inline.
    assert "NVDA — NVIDIA Corp. [INELIGIBLE]" in prompt
    # The agent is told to suggest only tickers that are not already present.
    lowered = prompt.lower()
    assert "not already in the roster" in lowered


def test_prompt_handles_empty_roster() -> None:
    summary = UniverseSummary(
        total=0,
        eligible_count=0,
        ineligible_count=0,
        category_counts={},
        sector_counts={},
        top_concentrations=[],
        unpriceable_listings=[],
        sector_roster=(),
    )
    prompt = build_universe_evaluation_prompt(summary)

    assert "Assets already in the universe (grouped by sector):\nnone" in prompt


def test_prompt_is_deterministic_for_a_fixed_summary() -> None:
    summary = _summary()

    assert build_universe_evaluation_prompt(summary) == (
        build_universe_evaluation_prompt(summary)
    )


def test_agent_instructions_forbid_suggesting_existing_holdings() -> None:
    instructions = agent_module._AGENT_INSTRUCTIONS.lower()

    assert "already in that roster" in instructions
    assert "not already present" in instructions


def test_evaluate_raises_domain_error_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NeverFinishes:
        @staticmethod
        async def run(*args: object, **kwargs: object) -> object:
            await asyncio.sleep(1)
            raise AssertionError("should have timed out")  # pragma: no cover

    monkeypatch.setattr(agent_module, "Runner", _NeverFinishes)
    monkeypatch.setattr(
        agent_module.settings, "RECOMMENDER_AGENT_TIMEOUT_SECONDS", 0
    )

    with pytest.raises(AssetEvaluationUnavailableError) as excinfo:
        OpenAIUniverseEvaluationAgent().evaluate(_summary())

    assert "timed out" in str(excinfo.value)


def test_evaluation_agent_uses_pydantic_output_type() -> None:
    agent = build_agent(
        name="AssetUniverseEvaluationAgent",
        instructions="x",
        output_type=UniverseEvaluationOutput,
    )
    assert agent.output_type is UniverseEvaluationOutput
