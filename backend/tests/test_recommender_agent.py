"""Unit tests for the recommender agent's prompt and structured-output wiring.

No network calls: these exercise the prompt builder and confirm the agent is
constructed with the Pydantic ``output_type``.
"""

from __future__ import annotations

from cadence.agents import build_agent
from cadence.agents.tools import web_search
from cadence.recommendations.agent import (
    EligibilityCriteria,
    RecommendationOutput,
    build_recommendation_prompt,
    default_eligibility_criteria,
)
from cadence.recommendations.composition import (
    CompositionEntry,
    UniverseComposition,
)


def _criteria() -> EligibilityCriteria:
    return EligibilityCriteria(
        min_price_eur=5,
        min_avg_daily_turnover_eur=2_000_000,
        min_market_cap_eur=1_000_000_000,
        min_history_years=5,
    )


def _empty_composition() -> UniverseComposition:
    return UniverseComposition(total=0, sectors=(), countries=())


def _populated_composition() -> UniverseComposition:
    return UniverseComposition(
        total=12,
        sectors=(
            CompositionEntry(key="technology", count=8),
            CompositionEntry(key="financial-services", count=4),
            CompositionEntry(key="energy", count=0),
        ),
        countries=(
            CompositionEntry(key="United States", count=9),
            CompositionEntry(key="Germany", count=3),
        ),
    )


def test_prompt_includes_categories_and_thresholds() -> None:
    prompt = build_recommendation_prompt(
        categories=["stock", "crypto"],
        count=7,
        criteria=_criteria(),
        composition=_empty_composition(),
        exclude_tickers=[],
    )

    assert "stock" in prompt
    assert "crypto" in prompt
    assert "7" in prompt
    # Thresholds appear (thousands-separated).
    assert "2,000,000" in prompt
    assert "1,000,000,000" in prompt
    assert "5 EUR" in prompt
    assert "5 years" in prompt


def test_prompt_includes_composition_and_diversification_steer() -> None:
    prompt = build_recommendation_prompt(
        categories=["stock"],
        count=3,
        criteria=_criteria(),
        composition=_populated_composition(),
        exclude_tickers=[],
    )

    # The current composition is surfaced, including a zero-count (absent) sector.
    assert "12 assets" in prompt
    assert "technology 8" in prompt
    assert "financial-services 4" in prompt
    assert "energy 0" in prompt
    assert "United States 9" in prompt
    assert "Germany 3" in prompt
    # The diversification steer and the major-index preference are present.
    assert "under-represented" in prompt
    for index_name in ("STOXX Europe 600", "DAX", "S&P 500", "Dow Jones"):
        assert index_name in prompt


def test_prompt_handles_empty_universe() -> None:
    prompt = build_recommendation_prompt(
        categories=["stock"],
        count=3,
        criteria=_criteria(),
        composition=_empty_composition(),
        exclude_tickers=[],
    )

    assert "currently empty" in prompt
    # The index preference is still expressed for an empty universe.
    assert "S&P 500" in prompt


def test_prompt_lists_excluded_tickers() -> None:
    prompt = build_recommendation_prompt(
        categories=["stock"],
        count=3,
        criteria=_criteria(),
        composition=_populated_composition(),
        exclude_tickers=["AAPL", "MSFT", "SAP.DE"],
    )

    # Each existing ticker is surfaced as a do-not-propose exclusion.
    assert "AAPL" in prompt
    assert "MSFT" in prompt
    assert "SAP.DE" in prompt
    assert "already in the universe" in prompt
    assert "Do NOT propose" in prompt


def test_default_criteria_match_asset_constants() -> None:
    from cadence.assets import constants as c

    criteria = default_eligibility_criteria()
    assert criteria.min_price_eur == c.MIN_PRICE_EUR
    assert criteria.min_avg_daily_turnover_eur == c.MIN_AVG_DAILY_TURNOVER_EUR
    assert criteria.min_market_cap_eur == c.MIN_MARKET_CAP_EUR
    assert criteria.min_history_years == c.MIN_HISTORY_YEARS


def test_recommender_agent_uses_pydantic_output_type() -> None:
    agent = build_agent(
        name="AssetRecommenderAgent",
        instructions="x",
        output_type=RecommendationOutput,
        tools=[web_search],
    )
    assert agent.output_type is RecommendationOutput
