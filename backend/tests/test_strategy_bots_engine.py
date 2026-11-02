"""Unit tests for the strategy-bot risk / execution engine against StubBroker."""

from __future__ import annotations

from datetime import UTC, datetime
from math import floor

from sqlalchemy.orm import Session

from cadence.assets.models import Asset
from cadence.broker.stub import StubBroker
from cadence.strategy_bots.engine import (
    REASON_DRAWDOWN,
    REASON_STOP_LOSS,
    REASON_TAKE_PROFIT,
    ExecutionEngine,
)
from cadence.strategy_bots.models import BotSession
from cadence.strategy_bots.strategy import Signal

_NOW = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)


def _make_bot(db_session: Session, ticker: str = "AAPL", **overrides: object) -> BotSession:
    """Create a flat bot session bound to a freshly-inserted universe asset."""
    asset = Asset(
        ticker=ticker,
        name=ticker,
        sector="technology",
        category="stock",
        currency="USD",
        is_eligible=True,
        criteria_results=[],
    )
    db_session.add(asset)
    db_session.flush()

    fields: dict[str, object] = {
        "strategy_key": "ma_crossover",
        "asset_id": asset.id,
        "ticker": ticker,
        "initial_capital": 100_000.0,
        "allocated_capital": 100_000.0,
        "strategy_params": {"fast_period": 2, "slow_period": 3},
        "drawdown_stop_pct": 0.25,
        "cash_buffer_pct": 0.02,
        "peak_value": 100_000.0,
    }
    fields.update(overrides)
    bot = BotSession(**fields)
    db_session.add(bot)
    db_session.flush()
    return bot


def _enter(engine: ExecutionEngine, bot: BotSession, broker: StubBroker) -> float:
    """Drive a full entry through the engine; return the entry price."""
    price = broker.get_quote(bot.ticker).last
    assert price is not None
    engine.run(bot, Signal.enter_long("test entry"), price, now=_NOW)
    return price


def test_enter_sizes_whole_shares_within_buffer(db_session: Session) -> None:
    broker = StubBroker()
    engine = ExecutionEngine(db_session, broker)
    bot = _make_bot(db_session)

    price = _enter(engine, bot, broker)
    expected_qty = floor((100_000.0 * 0.98) / price)

    assert bot.position_qty == expected_qty
    assert bot.position_avg_price == price
    assert bot.position_opened_at == _NOW
    assert bot.total_trades == 1
    assert len(bot.trades) == 1
    assert bot.trades[0].side == "buy"
    assert bot.trades[0].quantity == expected_qty


def test_no_pyramiding_when_already_long(db_session: Session) -> None:
    broker = StubBroker()
    engine = ExecutionEngine(db_session, broker)
    bot = _make_bot(db_session)

    _enter(engine, bot, broker)
    qty_before = bot.position_qty
    price = broker.get_quote(bot.ticker).last
    assert price is not None

    outcome = engine.run(bot, Signal.enter_long("again"), price, now=_NOW)

    assert outcome.action == "hold"
    assert bot.position_qty == qty_before
    assert bot.total_trades == 1


def test_exit_sells_whole_position(db_session: Session) -> None:
    broker = StubBroker()
    engine = ExecutionEngine(db_session, broker)
    bot = _make_bot(db_session)

    price = _enter(engine, bot, broker)
    outcome = engine.run(bot, Signal.exit("down cross"), price, now=_NOW)

    assert outcome.action == "exit"
    assert bot.is_flat
    assert bot.position_qty is None
    assert bot.total_trades == 2
    assert bot.trades[-1].side == "sell"


def test_exit_while_flat_never_opens_short(db_session: Session) -> None:
    broker = StubBroker()
    engine = ExecutionEngine(db_session, broker)
    bot = _make_bot(db_session)
    price = broker.get_quote(bot.ticker).last
    assert price is not None

    outcome = engine.run(bot, Signal.exit("down cross"), price, now=_NOW)

    assert outcome.action == "hold"
    assert outcome.trade is None
    assert bot.is_flat
    assert bot.total_trades == 0


def test_take_profit_exits_regardless_of_signal(db_session: Session) -> None:
    broker = StubBroker()
    engine = ExecutionEngine(db_session, broker)
    # High drawdown bound so only the take-profit fires.
    bot = _make_bot(db_session, take_profit_pct=0.05, drawdown_stop_pct=0.99)

    entry = _enter(engine, bot, broker)
    outcome = engine.run(bot, Signal.hold("no cross"), entry * 1.10, now=_NOW)

    assert outcome.action == "exit"
    assert outcome.trade is not None
    assert outcome.trade.reason == REASON_TAKE_PROFIT
    assert bot.is_flat


def test_stop_loss_exits_regardless_of_signal(db_session: Session) -> None:
    broker = StubBroker()
    engine = ExecutionEngine(db_session, broker)
    bot = _make_bot(db_session, stop_loss_pct=0.05, drawdown_stop_pct=0.99)

    entry = _enter(engine, bot, broker)
    outcome = engine.run(bot, Signal.hold("no cross"), entry * 0.90, now=_NOW)

    assert outcome.action == "exit"
    assert outcome.trade is not None
    assert outcome.trade.reason == REASON_STOP_LOSS
    assert bot.is_flat


def test_thresholds_unset_never_trigger(db_session: Session) -> None:
    broker = StubBroker()
    engine = ExecutionEngine(db_session, broker)
    bot = _make_bot(db_session, drawdown_stop_pct=0.99)

    entry = _enter(engine, bot, broker)
    qty = bot.position_qty
    # Big swings in both directions, but no TP/SL configured and no exit signal.
    engine.run(bot, Signal.hold("no cross"), entry * 1.50, now=_NOW)
    engine.run(bot, Signal.hold("no cross"), entry * 0.60, now=_NOW)

    assert not bot.is_flat
    assert bot.position_qty == qty
    assert bot.total_trades == 1


def test_drawdown_kill_switch_stops_and_flattens(db_session: Session) -> None:
    broker = StubBroker()
    engine = ExecutionEngine(db_session, broker)
    bot = _make_bot(db_session, drawdown_stop_pct=0.10)

    entry = _enter(engine, bot, broker)
    # A 20% price drop pushes total value well below the 10% drawdown floor.
    outcome = engine.run(bot, Signal.hold("no cross"), entry * 0.80, now=_NOW)

    assert outcome.action == "drawdown_stop"
    assert outcome.stopped is True
    assert bot.status == "stopped"
    assert bot.is_flat
    assert bot.trades[-1].reason == REASON_DRAWDOWN
