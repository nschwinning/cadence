"""Unit tests for the bot orchestrator's lifecycle and capital pool."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from cadence.assets.models import Asset
from cadence.bot_orchestrator import service
from cadence.bot_orchestrator.errors import (
    InvalidOrchestratorConfigError,
    OrchestratorNotArchivableError,
)
from cadence.bot_orchestrator.models import BotOrchestrator
from cadence.strategy_bots import service as bot_service
from cadence.strategy_bots.constants import BotOrigin
from cadence.strategy_bots.models import BotPosition, BotSession

_NOW = datetime(2026, 11, 10, 14, 0, tzinfo=UTC)


def _add_asset(db: Session, ticker: str = "AAPL") -> Asset:
    asset = Asset(
        ticker=ticker,
        name=ticker,
        sector="technology",
        category="stock",
        currency="USD",
        is_eligible=True,
        criteria_results=[],
    )
    db.add(asset)
    db.flush()
    return asset


def _orchestrator(db: Session, **overrides: object) -> BotOrchestrator:
    kwargs: dict[str, object] = {"label": "Core", "capital": 10_000.0}
    kwargs.update(overrides)
    return service.create_orchestrator(db, **kwargs)  # type: ignore[arg-type]


def _deploy(
    db: Session, orchestrator: BotOrchestrator, capital: float, ticker: str = "AAPL"
) -> BotSession:
    """Deploy a preset bot for ``orchestrator`` the way a run does (debit + create)."""
    orchestrator.free_capital -= capital
    return bot_service.create_bot_session(
        db,
        preset_key="ma_crossover_algo6",
        tickers=[ticker],
        initial_capital=capital,
        benchmark="SP500",
        origin=BotOrigin.ORCHESTRATOR,
        orchestrator_id=orchestrator.id,
    )


def _hold(db: Session, bot: BotSession, qty: float, price: float) -> None:
    symbol = bot.symbols[0]
    bot.positions.append(
        BotPosition(
            asset_id=symbol.asset_id,
            ticker=symbol.ticker,
            alpaca_symbol=symbol.alpaca_symbol,
            quantity=qty,
            avg_price=price,
            opened_at=_NOW,
        )
    )
    bot.cash -= qty * price
    db.flush()


# Lifecycle -------------------------------------------------------------------
def test_create_orchestrator_with_defaults(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)

    assert orchestrator.status == "active"
    assert orchestrator.free_capital == 10_000.0
    assert orchestrator.max_parallel_bots == 3
    assert orchestrator.max_bot_share == 0.5
    assert orchestrator.max_tickers_per_bot == 5
    assert orchestrator.cadence == "daily"
    assert orchestrator.benchmark == "SP500"
    assert orchestrator.model  # defaults to the configured AI model
    assert orchestrator.runs == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"label": "   "},
        {"capital": 4_999.0},
        {"max_parallel_bots": 0},
        {"max_parallel_bots": 11},
        {"max_bot_share": 0.0},
        {"max_bot_share": 1.5},
        {"max_tickers_per_bot": 0},
        {"max_tickers_per_bot": 11},
        {"cadence": "hourly"},
        {"model": "not-a-model"},
        {"benchmark": "NOPE"},
    ],
)
def test_create_orchestrator_rejects_invalid_config(
    db_session: Session, overrides: dict[str, object]
) -> None:
    with pytest.raises(InvalidOrchestratorConfigError):
        _orchestrator(db_session, **overrides)


def test_archive_requires_stopped(db_session: Session) -> None:
    orchestrator = _orchestrator(db_session)
    with pytest.raises(OrchestratorNotArchivableError):
        service.archive_orchestrator(db_session, orchestrator.id)

    service.stop_orchestrator(db_session, orchestrator.id)
    archived = service.archive_orchestrator(db_session, orchestrator.id)

    assert archived.status == "archived"
    assert archived.archived_at is not None
    assert service.list_orchestrators(db_session) == []
    assert service.list_orchestrators(db_session, include_archived=True) == [archived]


def test_stop_orchestrator_stops_its_bots(db_session: Session) -> None:
    _add_asset(db_session, "AAPL")
    _add_asset(db_session, "MSFT")
    orchestrator = _orchestrator(db_session)
    holding = _deploy(db_session, orchestrator, 3_000.0, "AAPL")
    _hold(db_session, holding, 10, 100.0)
    flat = _deploy(db_session, orchestrator, 2_000.0, "MSFT")

    service.stop_orchestrator(db_session, orchestrator.id)

    assert orchestrator.status == "stopped"
    assert orchestrator.stopped_at is not None
    assert {holding.status, flat.status} == {"stopped"}
    assert {holding.stop_reason, flat.stop_reason} == {"orchestrator"}
    # The flat bot returns its cash at once; the holding one waits for the tick.
    assert flat.capital_returned_at is not None
    assert holding.capital_returned_at is None
    assert orchestrator.free_capital == pytest.approx(10_000.0 - 3_000.0)


# Capital pool ----------------------------------------------------------------
def test_settle_returns_a_finished_bots_cash_once(db_session: Session) -> None:
    _add_asset(db_session)
    orchestrator = _orchestrator(db_session)
    bot = _deploy(db_session, orchestrator, 3_000.0)
    bot.cash = 3_240.0  # the bot made money before it was stopped and sold
    bot_service.stop_bot_session(db_session, bot.id)

    credited = service.settle_returned_capital(db_session, orchestrator)
    again = service.settle_returned_capital(db_session, orchestrator)

    assert credited == pytest.approx(3_240.0)
    assert again == 0.0
    assert orchestrator.free_capital == pytest.approx(7_000.0 + 3_240.0)
    assert bot.capital_returned_at is not None


def test_settle_skips_a_stopped_bot_still_holding_positions(
    db_session: Session,
) -> None:
    _add_asset(db_session)
    orchestrator = _orchestrator(db_session)
    bot = _deploy(db_session, orchestrator, 3_000.0)
    _hold(db_session, bot, 10, 100.0)
    bot_service.stop_bot_session(db_session, bot.id)

    assert service.settle_returned_capital(db_session, orchestrator) == 0.0
    assert bot.capital_returned_at is None
    assert orchestrator.free_capital == pytest.approx(7_000.0)


def test_settle_skips_active_bots(db_session: Session) -> None:
    _add_asset(db_session)
    orchestrator = _orchestrator(db_session)
    _deploy(db_session, orchestrator, 3_000.0)

    assert service.settle_returned_capital(db_session, orchestrator) == 0.0


def test_settle_all_covers_every_orchestrator(db_session: Session) -> None:
    _add_asset(db_session, "AAPL")
    _add_asset(db_session, "MSFT")
    first = _orchestrator(db_session, label="A")
    second = _orchestrator(db_session, label="B")
    bot_a = _deploy(db_session, first, 2_000.0, "AAPL")
    bot_b = _deploy(db_session, second, 1_500.0, "MSFT")
    bot_service.stop_bot_session(db_session, bot_a.id)
    bot_service.stop_bot_session(db_session, bot_b.id)

    credited = service.settle_all_returned_capital(db_session)

    assert credited == pytest.approx(3_500.0)
    assert first.free_capital == pytest.approx(10_000.0)
    assert second.free_capital == pytest.approx(10_000.0)


def test_figures_value_includes_unreturned_bots(db_session: Session) -> None:
    _add_asset(db_session, "AAPL")
    _add_asset(db_session, "MSFT")
    orchestrator = _orchestrator(db_session)
    active = _deploy(db_session, orchestrator, 3_000.0, "AAPL")
    finished = _deploy(db_session, orchestrator, 2_000.0, "MSFT")
    finished.cash = 2_100.0
    bot_service.stop_bot_session(db_session, finished.id)  # flat, not yet settled

    figures = service.orchestrator_figures(db_session, orchestrator)

    # free 5,000 + active bot (cash 3,000, no snapshot) + finished bot cash 2,100.
    assert figures.value == pytest.approx(5_000.0 + 3_000.0 + 2_100.0)
    assert figures.allocated_capital == pytest.approx(5_000.0)
    assert figures.active_bots == 1
    assert figures.liquidating_bots == 0
    assert figures.total_return_pct == pytest.approx(0.01)
    assert active.capital_returned_at is None

    # After settlement the value is unchanged; the bot simply moves into free capital.
    service.settle_returned_capital(db_session, orchestrator)
    after = service.orchestrator_figures(db_session, orchestrator)
    assert after.value == pytest.approx(figures.value)
    assert after.allocated_capital == pytest.approx(3_000.0)


def test_figures_count_liquidating_bots(db_session: Session) -> None:
    _add_asset(db_session)
    orchestrator = _orchestrator(db_session)
    bot = _deploy(db_session, orchestrator, 3_000.0)
    _hold(db_session, bot, 10, 100.0)
    bot_service.stop_bot_session(db_session, bot.id)

    figures = service.orchestrator_figures(db_session, orchestrator)

    assert figures.active_bots == 0
    assert figures.liquidating_bots == 1
