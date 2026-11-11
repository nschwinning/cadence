"""Signal-reconciliation guidance: rebalance prompt v7.

Tests build their schema with ``create_all`` rather than running migrations, so the
seeded prompt text is loaded straight from the v6 and v7 migration modules.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy.orm import Session
from tests.fakes import FakeAIPortfolioAgent
from tests.test_ai_portfolio_service import (
    _build_result,
    _flat_rebalance_result,
    _params,
    _seed_universe,
)

from cadence.ai_portfolio import service
from cadence.ai_portfolio.constants import (
    NEWS_SENTIMENT_PROMPT_VERSION,
    SIGNAL_RECONCILIATION_PROMPT_VERSION,
    EventStatus,
)
from cadence.ai_portfolio.models import RebalancePrompt
from cadence.broker.stub import StubBroker
from cadence.paper_trading import service as paper_service

_VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"
_SECTION_HEADING = "Reconciling multiple signals:"


def _load(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(filename, _VERSIONS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_V6 = _load("d7a9c2e4f6b8_seed_rebalance_prompt_v6.py")
_V7 = _load("9b2e4c6d8f01_seed_rebalance_prompt_v7.py")


def _section() -> str:
    """The inserted reconciliation section (everything v7 adds to v6)."""
    start = _V7._V7_INSTRUCTIONS.index(_SECTION_HEADING)
    end = _V7._V7_INSTRUCTIONS.index("Requirements:\n")
    return str(_V7._V7_INSTRUCTIONS[start:end])


# Seed text --------------------------------------------------------------------
def test_v7_is_v6_plus_the_reconciliation_section() -> None:
    assert SIGNAL_RECONCILIATION_PROMPT_VERSION == 7
    assert SIGNAL_RECONCILIATION_PROMPT_VERSION == NEWS_SENTIMENT_PROMPT_VERSION + 1
    assert _V7._V7_INSTRUCTIONS.replace(_section(), "") == _V6._V6_INSTRUCTIONS


def test_v7_input_template_is_byte_identical_to_v6() -> None:
    assert _V7._V7_INPUT_TEMPLATE == _V6._V6_INPUT_TEMPLATE


def test_section_covers_the_reconciliation_rules() -> None:
    section = _section()
    for phrase in (
        "ADVISORY input",
        "AGREE",
        "CONFLICT",
        "investment_thesis",
        "evaluation_summary",
        "not negative",
        "zero, one, or several",
        "long-only",
        "transaction-cost",
    ):
        assert phrase in section, phrase


# Rendering --------------------------------------------------------------------
def _seed_prompt(db: Session, module: ModuleType, version: int, prefix: str) -> None:
    db.add(
        RebalancePrompt(
            version=version,
            instructions=getattr(module, f"_{prefix}_INSTRUCTIONS"),
            input_template=getattr(module, f"_{prefix}_INPUT_TEMPLATE"),
        )
    )
    db.flush()


def _session(db: Session, broker: StubBroker, provider: object, **toggles: bool) -> Any:
    agent = FakeAIPortfolioAgent(build_result=_build_result("AAPL", "MSFT"))
    build_event = service.create_build_event(
        db, _params(allocated_capital=50_000.0, **toggles)
    )
    service.run_build_event(db, build_event.id, agent, broker, provider)
    session_id = service.get_event(db, build_event.id).session_id
    opening = service.create_rebalance_event(db, session_id)
    service.run_rebalance_event(db, opening.id, agent, broker, provider)
    return session_id


def _rebalance_instructions(
    db: Session, session_id: Any, broker: StubBroker, provider: object
) -> str:
    agent = FakeAIPortfolioAgent(rebalance_result=_flat_rebalance_result())
    event = service.create_rebalance_event(db, session_id)
    service.run_rebalance_event(db, event.id, agent, broker, provider)
    assert service.get_event(db, event.id).status == EventStatus.SUCCEEDED.value
    return str(agent.rebalance_calls[0]["instructions"])


def test_session_frozen_on_v6_keeps_v6_instructions(db_session: Session) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    _seed_prompt(db_session, _V6, 6, "V6")
    v6_session = _session(db_session, broker, provider)
    # v7 is seeded only after the v6 session was built, so that session stays on v6.
    _seed_prompt(db_session, _V7, 7, "V7")

    assert paper_service.get_session(db_session, v6_session).rebalance_prompt_version == 6
    instructions = _rebalance_instructions(db_session, v6_session, broker, provider)
    assert _SECTION_HEADING not in instructions


def test_session_on_v7_gets_the_section_with_no_signals_attached(
    db_session: Session,
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    _seed_prompt(db_session, _V6, 6, "V6")
    _seed_prompt(db_session, _V7, 7, "V7")
    session_id = _session(db_session, broker, provider)  # no opt-in signals

    assert paper_service.get_session(db_session, session_id).rebalance_prompt_version == 7
    instructions = _rebalance_instructions(db_session, session_id, broker, provider)
    assert _SECTION_HEADING in instructions


def test_session_on_v7_gets_the_section_with_one_signal_attached(
    db_session: Session,
) -> None:
    provider = _seed_universe(db_session, "AAPL", "MSFT")
    broker = StubBroker()
    _seed_prompt(db_session, _V6, 6, "V6")
    _seed_prompt(db_session, _V7, 7, "V7")
    session_id = _session(db_session, broker, provider, use_fundamentals=True)

    instructions = _rebalance_instructions(db_session, session_id, broker, provider)
    assert _SECTION_HEADING in instructions


def test_v7_renders_placeholders_and_keeps_literal_braces() -> None:
    from cadence.ai_portfolio.agent import _render

    rendered = _render(
        _V7._V7_INSTRUCTIONS, max_new_assets="5", max_web_searches="6"
    )

    assert "{max_new_assets}" not in rendered
    assert "at most 5 assets beyond the universe" in rendered
    assert '{"status": "unavailable"}' in rendered
    assert _SECTION_HEADING in rendered
