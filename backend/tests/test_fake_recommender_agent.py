"""The fake recommender agent must satisfy the RecommenderAgent Protocol."""

from __future__ import annotations

import pytest
from tests.fakes import FakeRecommenderAgent

from cadence.recommendations.agent import (
    RecommendationCandidate,
    RecommenderAgent,
    default_eligibility_criteria,
)
from cadence.recommendations.composition import UniverseComposition

_EMPTY_COMPOSITION = UniverseComposition(total=0, sectors=(), countries=())


def test_fake_satisfies_protocol_and_returns_candidates() -> None:
    fake = FakeRecommenderAgent(
        candidates=[RecommendationCandidate(ticker="AAPL", rationale="liquid")],
        tool_call_count=3,
    )
    assert isinstance(fake, RecommenderAgent)

    result = fake.recommend(
        categories=["stock"],
        count=5,
        criteria=default_eligibility_criteria(),
        composition=_EMPTY_COMPOSITION,
    )
    assert result.tool_call_count == 3
    assert [c.ticker for c in result.output.candidates] == ["AAPL"]
    assert fake.recommend_calls == [(["stock"], 5)]


def test_fake_can_raise() -> None:
    fake = FakeRecommenderAgent(error=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        fake.recommend(
            categories=["stock"],
            count=5,
            criteria=default_eligibility_criteria(),
            composition=_EMPTY_COMPOSITION,
        )
