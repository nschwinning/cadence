"""Integration tests for the recommender service against Postgres."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session
from tests.fakes import FakeMarketDataProvider, FakeRecommenderAgent

from cadence.assets import service as assets_service
from cadence.assets.market_data import AssetInfo, HistoryBar
from cadence.recommendations import service
from cadence.recommendations.agent import RecommendationCandidate
from cadence.recommendations.constants import CandidateOutcome, RunPhase
from cadence.recommendations.errors import RecommendationValidationError


def _eligible_provider(market_cap: float = 5_000_000_000.0) -> FakeMarketDataProvider:
    return FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Test Co",
            exchange="XETRA",
            currency="EUR",
            price=50.0,
            market_cap=market_cap,
            quote_type="EQUITY",
        ),
        history=[
            HistoryBar(date=date(2005, 1, 1), close=50.0, volume=1_000_000.0),
            HistoryBar(date=date(2024, 1, 1), close=50.0, volume=1_000_000.0),
        ],
    )


def _ineligible_provider() -> FakeMarketDataProvider:
    # Market cap below the 1B EUR threshold -> not eligible.
    return _eligible_provider(market_cap=500_000_000.0)


def _eligible_provider_with_profile() -> FakeMarketDataProvider:
    """An eligible provider whose info carries a sector and country, so a seeded
    asset contributes to the universe composition the recommender snapshots."""
    return FakeMarketDataProvider(
        info=AssetInfo(
            company_name="Seed Co",
            exchange="XETRA",
            currency="EUR",
            price=50.0,
            market_cap=5_000_000_000.0,
            quote_type="EQUITY",
            sector_key="technology",
            country="Germany",
        ),
        history=[
            HistoryBar(date=date(2005, 1, 1), close=50.0, volume=1_000_000.0),
            HistoryBar(date=date(2024, 1, 1), close=50.0, volume=1_000_000.0),
        ],
    )


def _agent(tickers: list[str], tool_call_count: int = 2) -> FakeRecommenderAgent:
    return FakeRecommenderAgent(
        candidates=[
            RecommendationCandidate(ticker=t, rationale="because") for t in tickers
        ],
        tool_call_count=tool_call_count,
    )


# --- 4.1 create_run ---------------------------------------------------------


def test_create_run_happy_path(db_session: Session) -> None:
    run_id = service.create_run(db_session, count=3, categories=["stock"])

    run = service.get_run(db_session, run_id)
    assert run.status == RunPhase.QUEUED.value
    assert run.requested_count == 3
    assert run.requested_categories == ["stock"]
    assert run.results == []


def test_create_run_rejects_nonpositive_count(db_session: Session) -> None:
    with pytest.raises(RecommendationValidationError):
        service.create_run(db_session, count=0, categories=["stock"])


def test_create_run_rejects_empty_categories(db_session: Session) -> None:
    with pytest.raises(RecommendationValidationError):
        service.create_run(db_session, count=3, categories=[])


def test_create_run_rejects_unsupported_categories(db_session: Session) -> None:
    # Only stock and crypto are supported; anything else is rejected.
    with pytest.raises(RecommendationValidationError):
        service.create_run(db_session, count=3, categories=["etf"])
    with pytest.raises(RecommendationValidationError):
        service.create_run(db_session, count=3, categories=["stock", "fund"])


def test_create_run_accepts_stock_and_crypto(db_session: Session) -> None:
    run_id = service.create_run(db_session, count=3, categories=["stock", "crypto"])
    run = service.get_run(db_session, run_id)
    assert run.requested_categories == ["stock", "crypto"]


# --- 4.2 executor drives to completed --------------------------------------


def test_execute_run_completes_and_records_prompt_and_tool_calls(
    db_session: Session,
) -> None:
    run_id = service.create_run(db_session, count=1, categories=["stock"])
    agent = _agent(["AAA"], tool_call_count=4)

    service.execute_run(db_session, run_id, agent, _eligible_provider())

    run = service.get_run(db_session, run_id)
    assert run.status == RunPhase.COMPLETED.value
    assert run.tool_call_count == 4
    assert run.prompt is not None and "stock" in run.prompt
    assert run.error is None


def test_execute_run_prompt_reflects_universe_composition(
    db_session: Session,
) -> None:
    # The recommender now snapshots the real universe composition (via the
    # dashboard aggregation). Seeding a technology/Germany asset means the
    # recorded prompt carries that composition so the agent is steered with it.
    assets_service.add_asset(db_session, "SEED", _eligible_provider_with_profile())

    run_id = service.create_run(db_session, count=1, categories=["stock"])
    agent = _agent(["AAA"])

    service.execute_run(db_session, run_id, agent, _eligible_provider())

    run = service.get_run(db_session, run_id)
    assert run.prompt is not None
    # The diversification steer and the seeded composition are in the prompt.
    assert "under-represented" in run.prompt
    assert "technology 1" in run.prompt
    assert "Germany 1" in run.prompt
    # The major-index preference is expressed too.
    assert "S&P 500" in run.prompt


# --- 4.3 hard eligibility filter + duplicate classification ----------------


def _tickers(db_session: Session) -> set[str]:
    return {a.ticker for a in assets_service.list_assets(db_session)}


def test_ineligible_candidate_not_persisted_and_recorded(
    db_session: Session,
) -> None:
    run_id = service.create_run(db_session, count=2, categories=["stock"])
    agent = _agent(["BAD"])

    service.execute_run(db_session, run_id, agent, _ineligible_provider())

    run = service.get_run(db_session, run_id)
    assert run.status == RunPhase.COMPLETED.value
    assert run.results == [
        {"ticker": "BAD", "outcome": CandidateOutcome.SKIPPED_INELIGIBLE.value, "detail": None}
    ]
    # The ineligible asset was not kept in the universe.
    assert "BAD" not in _tickers(db_session)


def test_duplicate_candidate_recorded_as_skipped(db_session: Session) -> None:
    assets_service.add_asset(db_session, "DUP", _eligible_provider())

    run_id = service.create_run(db_session, count=2, categories=["stock"])
    agent = _agent(["DUP"])
    service.execute_run(db_session, run_id, agent, _eligible_provider())

    run = service.get_run(db_session, run_id)
    outcomes = {r["ticker"]: r["outcome"] for r in run.results}
    assert outcomes["DUP"] == CandidateOutcome.SKIPPED_DUPLICATE.value


def test_execute_run_passes_existing_tickers_as_exclusions(
    db_session: Session,
) -> None:
    # Seed the universe; the recommender must be told to exclude those tickers
    # (and the recorded prompt must list them) so it stops re-proposing them.
    assets_service.add_asset(db_session, "SEED", _eligible_provider())

    run_id = service.create_run(db_session, count=1, categories=["stock"])
    agent = _agent(["NEW"])
    service.execute_run(db_session, run_id, agent, _eligible_provider())

    assert agent.exclude_calls == [["SEED"]]
    run = service.get_run(db_session, run_id)
    assert run.prompt is not None
    assert "SEED" in run.prompt
    assert "already in the universe" in run.prompt


# --- 4.4 count upper bound --------------------------------------------------


def test_added_assets_capped_at_requested_count(db_session: Session) -> None:
    run_id = service.create_run(db_session, count=2, categories=["stock"])
    agent = _agent(["AAA", "BBB", "CCC", "DDD"])

    before = _tickers(db_session)
    service.execute_run(db_session, run_id, agent, _eligible_provider())

    run = service.get_run(db_session, run_id)
    added = [
        r["ticker"] for r in run.results if r["outcome"] == CandidateOutcome.ADDED.value
    ]
    assert len(added) == 2
    # Exactly two of the four candidates entered the universe.
    newly_added = _tickers(db_session) - before
    assert newly_added == set(added)
    assert len(newly_added) == 2
    assert {"CCC", "DDD"}.isdisjoint(newly_added)


# --- 4.5 failure handling ---------------------------------------------------


def test_failed_run_records_reason_and_keeps_prior_assets(
    db_session: Session,
) -> None:
    # A pre-existing asset must survive a later failing run.
    assets_service.add_asset(db_session, "KEEP", _eligible_provider())

    run_id = service.create_run(db_session, count=2, categories=["stock"])
    agent = FakeRecommenderAgent(error=RuntimeError("agent exploded"))

    service.execute_run(db_session, run_id, agent, _eligible_provider())

    run = service.get_run(db_session, run_id)
    assert run.status == RunPhase.FAILED.value
    assert run.error is not None and "exploded" in run.error
    # The asset added before the failing run survives.
    assert "KEEP" in _tickers(db_session)
