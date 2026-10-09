"""Integration tests for the universe-evaluation service (fake agent, Postgres).

Exercise the summary, the deterministic fingerprint, and the generate/get/
outdated flow without any network access.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session
from tests.fakes import FakeUniverseEvaluationAgent

from cadence.api.schemas import AssetUniverseEvaluationRead
from cadence.assets import service
from cadence.assets.category import AssetCategory
from cadence.assets.errors import AssetEvaluationUnavailableError
from cadence.assets.models import Asset, AssetUniverseEvaluation
from cadence.assets.universe_agent import UniverseEvaluationOutput

_UNSET = object()


def _asset(
    ticker: str,
    *,
    category: str = AssetCategory.STOCK.value,
    sector: str | None = "technology",
    is_eligible: bool = True,
    market_cap_usd: float | None = 5_000_000_000.0,
    alpaca_symbol: str | None | object = _UNSET,
    currency: str = "USD",
) -> Asset:
    return Asset(
        ticker=ticker,
        name=f"{ticker} Co",
        alpaca_symbol=ticker if alpaca_symbol is _UNSET else alpaca_symbol,
        fractionable=True,
        category=category,
        sector=sector,
        exchange="XETRA",
        currency=currency,
        country="United States",
        is_eligible=is_eligible,
        market_cap_usd=market_cap_usd,
        avg_daily_turnover_usd=10_000_000.0,
        history_years=10.0,
        criteria_results=[],
    )


def _seed(db_session: Session, assets: list[Asset]) -> None:
    for asset in assets:
        db_session.add(asset)
    db_session.commit()


# --- summary -----------------------------------------------------------------


def test_universe_summary_counts(db_session: Session) -> None:
    assets = [
        _asset("AAA", sector="technology"),
        _asset("BBB", sector="technology"),
        _asset("CCC", sector="energy", is_eligible=False),
        _asset("DDD", category=AssetCategory.CRYPTO.value, sector=None),
        _asset("AIR.PA", sector="industrials", alpaca_symbol=None),
    ]
    _seed(db_session, assets)

    summary = service._universe_summary(service.get_universe_assets(db_session))

    assert summary.total == 5
    assert summary.eligible_count == 4
    assert summary.ineligible_count == 1
    assert summary.category_counts == {"stock": 4, "crypto": 1}
    assert summary.sector_counts == {
        "technology": 2,
        "energy": 1,
        "none": 1,
        "industrials": 1,
    }
    assert summary.top_concentrations[0] == ("technology", 2)
    assert summary.unpriceable_listings == ["AIR.PA"]


# --- fingerprint -------------------------------------------------------------


def test_fingerprint_stable_and_order_independent() -> None:
    a = _asset("AAA")
    b = _asset("BBB")
    assert service._universe_fingerprint([a, b]) == service._universe_fingerprint(
        [b, a]
    )


def test_fingerprint_changes_on_add_remove() -> None:
    a = _asset("AAA")
    b = _asset("BBB")
    base = service._universe_fingerprint([a])
    assert service._universe_fingerprint([a, b]) != base
    assert service._universe_fingerprint([]) != base


def test_fingerprint_changes_on_metric_and_eligibility() -> None:
    base = service._universe_fingerprint([_asset("AAA")])
    assert (
        service._universe_fingerprint([_asset("AAA", market_cap_usd=1.0)]) != base
    )
    assert (
        service._universe_fingerprint([_asset("AAA", is_eligible=False)]) != base
    )


def test_fingerprint_ignores_untracked_attributes() -> None:
    """A change to an attribute outside the tracked set does not flip the hash."""
    a = _asset("AAA")
    base = service._universe_fingerprint([a])
    a.city = "Berlin"  # city is not part of the fingerprint
    assert service._universe_fingerprint([a]) == base


# --- generate / get / outdated ----------------------------------------------


def test_generate_persists_single_row(db_session: Session) -> None:
    _seed(db_session, [_asset("AAA"), _asset("BBB")])
    agent = FakeUniverseEvaluationAgent()

    evaluation = service.generate_evaluation(
        db_session, agent, service.get_universe_assets(db_session)
    )

    assert evaluation is not None
    assert len(agent.evaluate_calls) == 1
    assert db_session.query(AssetUniverseEvaluation).count() == 1
    stored = service.get_evaluation(db_session)
    assert stored is not None
    assert stored.narrative == "A reasonably diversified universe."


def test_regenerate_replaces_record(db_session: Session) -> None:
    _seed(db_session, [_asset("AAA")])
    first = service.generate_evaluation(
        db_session,
        FakeUniverseEvaluationAgent(),
        service.get_universe_assets(db_session),
    )
    assert first is not None
    first_id = first.id

    second_agent = FakeUniverseEvaluationAgent(
        output=UniverseEvaluationOutput(
            narrative="Updated assessment.",
            strengths=[],
            concerns=[],
            suggestions=[],
        )
    )
    second = service.generate_evaluation(
        db_session, second_agent, service.get_universe_assets(db_session)
    )

    assert second is not None
    assert second.id == first_id  # same single row, replaced in place
    assert db_session.query(AssetUniverseEvaluation).count() == 1
    assert service.get_evaluation(db_session).narrative == "Updated assessment."


def test_outdated_false_when_unchanged_true_after_change(
    db_session: Session,
) -> None:
    _seed(db_session, [_asset("AAA")])
    evaluation = service.generate_evaluation(
        db_session,
        FakeUniverseEvaluationAgent(),
        service.get_universe_assets(db_session),
    )
    assert evaluation is not None

    assert (
        service.evaluation_outdated(
            evaluation, service.get_universe_assets(db_session)
        )
        is False
    )

    _seed(db_session, [_asset("BBB")])
    assert (
        service.evaluation_outdated(
            evaluation, service.get_universe_assets(db_session)
        )
        is True
    )


def test_generate_empty_universe_returns_none_without_calling_agent(
    db_session: Session,
) -> None:
    agent = FakeUniverseEvaluationAgent()

    result = service.generate_evaluation(
        db_session, agent, service.get_universe_assets(db_session)
    )

    assert result is None
    assert agent.evaluate_calls == []
    assert db_session.query(AssetUniverseEvaluation).count() == 0


def test_read_schema_maps_from_orm_row_with_outdated(db_session: Session) -> None:
    _seed(db_session, [_asset("AAA")])
    evaluation = service.generate_evaluation(
        db_session,
        FakeUniverseEvaluationAgent(),
        service.get_universe_assets(db_session),
    )
    assert evaluation is not None
    # ``outdated`` is a transient attribute the router attaches before validation.
    evaluation.outdated = True  # type: ignore[attr-defined]

    read = AssetUniverseEvaluationRead.model_validate(evaluation)

    assert read.narrative == "A reasonably diversified universe."
    assert read.strengths == ["Broad sector coverage"]
    assert read.concerns == ["Some concentration in technology"]
    assert read.suggestions == ["Add exposure to utilities"]
    assert read.outdated is True
    assert read.generated_at == evaluation.generated_at


def test_agent_failure_leaves_existing_row_intact(db_session: Session) -> None:
    _seed(db_session, [_asset("AAA")])
    service.generate_evaluation(
        db_session,
        FakeUniverseEvaluationAgent(),
        service.get_universe_assets(db_session),
    )
    _seed(db_session, [_asset("BBB")])  # make it outdated

    failing = FakeUniverseEvaluationAgent(
        error=AssetEvaluationUnavailableError("provider down")
    )
    with pytest.raises(AssetEvaluationUnavailableError):
        service.generate_evaluation(
            db_session, failing, service.get_universe_assets(db_session)
        )

    # The prior evaluation survives unchanged.
    assert db_session.query(AssetUniverseEvaluation).count() == 1
    assert service.get_evaluation(db_session).narrative == (
        "A reasonably diversified universe."
    )
