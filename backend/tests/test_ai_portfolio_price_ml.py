"""Tests for the learned price-direction (price-ML) rebalance integration.

The helper-level tests exercise the gate-controlled attachment onto candidate /
holding dicts in isolation (no DB, no agent), mirroring
``test_ai_portfolio_fundamentals.py``. The flow-level tests drive a real build +
rebalance and assert the end-to-end gate: a session opted into price-ML and frozen
on the price-ML-aware prompt version attaches the block to the agent's candidates
and holdings; an opted-out session, or one frozen on an older prompt version,
attaches nothing; a stored signal surfaces as ``available`` while an asset with no
signal is explicitly marked ``unavailable`` (never fabricated); and a rebalance
still proceeds when no signals exist at all.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.fakes import FakeAIPortfolioAgent
from tests.test_ai_portfolio_service import (  # reuse the flow harness
    _build_result,
    _flat_rebalance_result,
    _params,
    _seed_universe,
)

from cadence.ai_portfolio import service
from cadence.ai_portfolio._helpers import _build_holdings, _candidates_from_universe
from cadence.ai_portfolio.constants import (
    FUNDAMENTALS_PROMPT_VERSION,
    PRICE_ML_PROMPT_VERSION,
    EventStatus,
)
from cadence.ai_portfolio.models import RebalancePrompt
from cadence.assets.models import Asset
from cadence.broker.stub import StubBroker
from cadence.paper_trading import service as paper_service
from cadence.paper_trading.models import SessionPosition
from cadence.price_ml import constants as price_ml_constants
from cadence.price_ml import service as price_ml_service
from cadence.price_ml.constants import SignalDirection

# --------------------------------------------------------------------------- #
# Version constant
# --------------------------------------------------------------------------- #


def test_price_ml_prompt_version_is_after_fundamentals() -> None:
    assert PRICE_ML_PROMPT_VERSION > FUNDAMENTALS_PROMPT_VERSION
    assert PRICE_ML_PROMPT_VERSION == 5


# --------------------------------------------------------------------------- #
# Build params round-trip
# --------------------------------------------------------------------------- #


def test_ai_build_params_price_ml_round_trip() -> None:
    # The price-ML opt-in must survive to_payload -> from_payload, and default off.
    from cadence.ai_portfolio.service import AIBuildParams

    assert AIBuildParams(allocated_capital=1.0).use_price_ml is False
    params = AIBuildParams(allocated_capital=50_000.0, use_price_ml=True)
    restored = AIBuildParams.from_payload(params.to_payload())
    assert restored == params
    assert restored.use_price_ml is True
    # A legacy payload with no key degrades to opted out.
    legacy = AIBuildParams.from_payload({"allocated_capital": 1.0})
    assert legacy.use_price_ml is False


# --------------------------------------------------------------------------- #
# Candidate / holding attach helpers (no DB)
# --------------------------------------------------------------------------- #


def _asset(ticker: str) -> Asset:
    return Asset(
        ticker=ticker,
        name=ticker,
        sector="technology",
        category="stock",
        is_eligible=True,
    )


def _ledger(*tickers: str) -> list[SessionPosition]:
    return [SessionPosition(ticker=t, quantity=10.0, avg_cost=50.0) for t in tickers]


def test_candidates_attach_price_ml_when_map_given() -> None:
    assets = [_asset("AAPL"), _asset("NOSIG")]
    candidates, _ = _candidates_from_universe(
        assets,
        {},
        apply_gate=False,
        price_ml_by_ticker={
            "AAPL": {"status": "available", "direction": "up", "probability": 0.7}
        },
    )
    by_ticker = {c["ticker"]: c for c in candidates}
    assert by_ticker["AAPL"]["price_ml"]["status"] == "available"
    assert by_ticker["AAPL"]["price_ml"]["direction"] == "up"
    # A ticker missing from the map -> explicit unavailable marker, not fabricated.
    assert by_ticker["NOSIG"]["price_ml"] == {"status": "unavailable"}


def test_candidates_omit_price_ml_when_map_none() -> None:
    candidates, _ = _candidates_from_universe(
        [_asset("AAPL")], {}, apply_gate=False, price_ml_by_ticker=None
    )
    assert all("price_ml" not in c for c in candidates)


def test_holdings_attach_price_ml_when_map_given() -> None:
    broker = StubBroker()
    holdings = _build_holdings(
        _ledger("AAPL", "MSFT"),
        broker,
        {},
        price_ml_by_ticker={
            "AAPL": {"status": "available", "direction": "down", "probability": 0.6}
        },
    )
    by_ticker = {h["ticker"]: h for h in holdings}
    assert by_ticker["AAPL"]["price_ml"] == {
        "status": "available",
        "direction": "down",
        "probability": 0.6,
    }
    # A held ticker absent from the map falls back to the unavailable marker.
    assert by_ticker["MSFT"]["price_ml"] == {"status": "unavailable"}


def test_holdings_omit_price_ml_when_map_none() -> None:
    broker = StubBroker()
    holdings = _build_holdings(_ledger("AAPL"), broker, {})
    assert all("price_ml" not in h for h in holdings)


# --------------------------------------------------------------------------- #
# Flow-level gate (build + rebalance)
# --------------------------------------------------------------------------- #


def _seed_v5_prompt(db_session: Session) -> None:
    """Make the price-ML-aware version (5) the active rebalance prompt."""
    db_session.add(
        RebalancePrompt(
            version=PRICE_ML_PROMPT_VERSION,
            instructions="v5 instructions {max_new_assets}",
            input_template="v5 input {risk_profile} {candidates_json}",
        )
    )
    db_session.flush()


def _asset_id(db_session: Session, ticker: str) -> int:
    return db_session.execute(
        select(Asset.id).where(Asset.ticker == ticker)
    ).scalar_one()


def _store_signal(db_session: Session, ticker: str, direction: str = "up") -> None:
    price_ml_service.record_signal(
        db_session,
        asset_id=_asset_id(db_session, ticker),
        as_of_date=price_ml_constants.today(),
        horizon_days=21,
        direction=direction,
        probability=0.72,
        recent_oos_accuracy=0.58,
        model_version="test-v1",
        feature_as_of=price_ml_constants.today(),
        bar_count=300,
    )


def _build_opted_in_session(
    db_session: Session,
    broker: StubBroker,
    provider: object,
    *,
    use_price_ml: bool,
    seed_v5: bool,
) -> object:
    """Build a session (optionally opted into price-ML and frozen on v5) and run its
    opening allocation so it holds AAPL + MSFT."""
    if seed_v5:
        _seed_v5_prompt(db_session)
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    build_event = service.create_build_event(
        db_session, _params(allocated_capital=50_000.0, use_price_ml=use_price_ml)
    )
    service.run_build_event(db_session, build_event.id, agent, broker, provider)
    session_id = service.get_event(db_session, build_event.id).session_id
    opening = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, opening.id, agent, broker, provider)
    return session_id


def test_rebalance_attaches_price_ml_when_opted_in(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id = _build_opted_in_session(
        db_session, broker, provider, use_price_ml=True, seed_v5=True
    )
    session_row = paper_service.get_session(db_session, session_id)
    assert session_row.use_price_ml is True
    assert session_row.rebalance_prompt_version == PRICE_ML_PROMPT_VERSION

    # A stored signal for AAPL surfaces as available; MSFT has none -> unavailable.
    _store_signal(db_session, "AAPL", direction=SignalDirection.UP.value)

    rebalance = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    rb = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb.id, rebalance, broker, provider)

    assert service.get_event(db_session, rb.id).status == EventStatus.SUCCEEDED.value
    call = rebalance.rebalance_calls[0]
    cands = {c["ticker"]: c for c in call["candidates"]}
    assert cands["AAPL"]["price_ml"]["status"] == "available"
    assert cands["AAPL"]["price_ml"]["direction"] == SignalDirection.UP.value
    assert cands["AAPL"]["price_ml"]["recent_oos_accuracy"] == 0.58
    assert cands["MSFT"]["price_ml"] == {"status": "unavailable"}
    holds = {h["ticker"]: h for h in call["holdings"]}
    assert holds["AAPL"]["price_ml"]["status"] == "available"
    assert holds["MSFT"]["price_ml"] == {"status": "unavailable"}


def test_rebalance_omits_price_ml_when_opted_out(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    # Opted out (default) but v5 is still active: the gate must stay off.
    session_id = _build_opted_in_session(
        db_session, broker, provider, use_price_ml=False, seed_v5=True
    )
    _store_signal(db_session, "AAPL")

    rebalance = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    rb = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb.id, rebalance, broker, provider)

    call = rebalance.rebalance_calls[0]
    assert all("price_ml" not in c for c in call["candidates"])
    assert all("price_ml" not in h for h in call["holdings"])


def test_rebalance_omits_price_ml_when_frozen_version_too_old(
    db_session: Session,
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    # Opted in, but no v5 prompt: the session freezes conftest's v1 (< 5), so the
    # gate stays off even though the flag is on.
    session_id = _build_opted_in_session(
        db_session, broker, provider, use_price_ml=True, seed_v5=False
    )
    session_row = paper_service.get_session(db_session, session_id)
    assert session_row.use_price_ml is True
    assert session_row.rebalance_prompt_version < PRICE_ML_PROMPT_VERSION
    _store_signal(db_session, "AAPL")

    rebalance = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    rb = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb.id, rebalance, broker, provider)

    call = rebalance.rebalance_calls[0]
    assert all("price_ml" not in c for c in call["candidates"])
    assert all("price_ml" not in h for h in call["holdings"])


def test_initial_allocation_inherits_price_ml(db_session: Session) -> None:
    # The opening allocation now runs as the session's first rebalance, so it
    # inherits the price-ML block with no extra wiring. Store the signal BEFORE the
    # opening allocation and assert its agent call already carries the block.
    _seed_v5_prompt(db_session)
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    build_event = service.create_build_event(
        db_session, _params(allocated_capital=50_000.0, use_price_ml=True)
    )
    service.run_build_event(db_session, build_event.id, agent, broker, provider)
    session_id = service.get_event(db_session, build_event.id).session_id

    _store_signal(db_session, "AAPL", direction=SignalDirection.UP.value)

    opening = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, opening.id, agent, broker, provider)

    assert (
        service.get_event(db_session, opening.id).status
        == EventStatus.SUCCEEDED.value
    )
    # The opening allocation is the agent's first rebalance call.
    call = agent.rebalance_calls[0]
    cands = {c["ticker"]: c for c in call["candidates"]}
    assert cands["AAPL"]["price_ml"]["status"] == "available"
    assert cands["AAPL"]["price_ml"]["direction"] == SignalDirection.UP.value
    assert cands["MSFT"]["price_ml"] == {"status": "unavailable"}


def test_rebalance_proceeds_when_no_signals_stored(db_session: Session) -> None:
    # The degradation contract: an opted-in session with NO stored signals still
    # rebalances; every name carries the explicit unavailable marker, never a
    # fabricated direction.
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    session_id = _build_opted_in_session(
        db_session, broker, provider, use_price_ml=True, seed_v5=True
    )

    rebalance = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    rb = service.create_rebalance_event(db_session, session_id)
    service.run_rebalance_event(db_session, rb.id, rebalance, broker, provider)

    assert service.get_event(db_session, rb.id).status == EventStatus.SUCCEEDED.value
    call = rebalance.rebalance_calls[0]
    assert call["candidates"], "expected candidates were assembled"
    assert all(c["price_ml"] == {"status": "unavailable"} for c in call["candidates"])
    assert all(h["price_ml"] == {"status": "unavailable"} for h in call["holdings"])
