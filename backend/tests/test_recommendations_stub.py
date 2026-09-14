"""Tests for the offline stub recommender used by the Docker smoke / dev."""

from __future__ import annotations

from cadence.recommendations.agent import (
    RecommenderAgent,
    default_eligibility_criteria,
)
from cadence.recommendations.composition import UniverseComposition
from cadence.recommendations.stub import StubRecommenderAgent

_EMPTY_COMPOSITION = UniverseComposition(total=0, sectors=(), countries=())


def test_stub_satisfies_recommender_protocol() -> None:
    assert isinstance(StubRecommenderAgent(), RecommenderAgent)


def test_stub_returns_canned_candidates_and_tool_call_count() -> None:
    stub = StubRecommenderAgent()
    criteria = default_eligibility_criteria()

    result = stub.recommend(
        categories=["stock"],
        count=2,
        criteria=criteria,
        composition=_EMPTY_COMPOSITION,
    )

    tickers = [c.ticker for c in result.output.candidates]
    assert tickers  # non-empty pool
    assert len(set(tickers)) == len(tickers)  # deduped
    # Simulated one tool call per candidate.
    assert result.tool_call_count == len(tickers)


def test_stub_unions_pools_across_categories_without_duplicates() -> None:
    stub = StubRecommenderAgent()
    criteria = default_eligibility_criteria()

    result = stub.recommend(
        categories=["stock", "etf"],
        count=5,
        criteria=criteria,
        composition=_EMPTY_COMPOSITION,
    )

    tickers = [c.ticker for c in result.output.candidates]
    assert "SPY" in tickers  # etf pool contributed
    assert "NVDA" in tickers  # stock pool contributed
    assert len(set(tickers)) == len(tickers)


def test_stub_prompt_embeds_categories_and_thresholds() -> None:
    stub = StubRecommenderAgent()
    criteria = default_eligibility_criteria()

    prompt = stub.build_prompt(
        categories=["stock"],
        count=3,
        criteria=criteria,
        composition=_EMPTY_COMPOSITION,
    )

    assert "stock" in prompt
    assert f"{criteria.min_market_cap_eur:,.0f}" in prompt
