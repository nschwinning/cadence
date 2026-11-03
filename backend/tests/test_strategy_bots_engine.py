"""Unit tests for the strategy-bot execution engine + pure value helpers.

The engine is now a primitive layer: ``enter`` buys and creates a position debiting
the shared cash pool; ``exit`` sells a position fully, crediting cash and realised
P&L. Orchestration (TP/SL, drawdown, ordering) lives in the service tick, tested
separately. The pure ``unrealised_pnl`` / ``total_value`` / ``take_profit_stop_loss_reason``
helpers are covered here too.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from cadence.assets.models import Asset
from cadence.broker.stub import StubBroker
from cadence.strategy_bots.engine import (
    REASON_STOP_LOSS,
    REASON_TAKE_PROFIT,
    ExecutionEngine,
    take_profit_stop_loss_reason,
    total_value,
    unrealised_pnl,
)
from cadence.strategy_bots.models import BotPosition, BotSession

_NOW = datetime(2026, 1, 2, 15, 0, tzinfo=UTC)


def _add_asset(db_session: Session, ticker: str) -> Asset:
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
    return asset


def _make_bot(db_session: Session, **overrides: object) -> BotSession:
    """A flat multi-asset bot with a full shared cash pool."""
    fields: dict[str, object] = {
        "strategy_key": "ma_crossover",
        "initial_capital": 100_000.0,
        "allocated_capital": 100_000.0,
        "cash": 100_000.0,
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


def test_enter_creates_position_and_debits_cash(db_session: Session) -> None:
    broker = StubBroker()
    engine = ExecutionEngine(db_session, broker)
    asset = _add_asset(db_session, "AAPL")
    bot = _make_bot(db_session)
    price = broker.get_quote("AAPL").last
    assert price is not None

    outcome = engine.enter(
        bot,
        asset_id=asset.id,
        ticker="AAPL",
        symbol="AAPL",
        shares=10,
        price=price,
        now=_NOW,
        reason="up cross",
    )

    assert outcome.action == "enter"
    assert len(bot.positions) == 1
    pos = bot.positions[0]
    assert pos.quantity == 10
    assert pos.avg_price == price
    assert bot.cash == 100_000.0 - 10 * price
    assert bot.total_trades == 1
    assert bot.trades[0].side == "buy"


def test_enter_zero_shares_is_noop(db_session: Session) -> None:
    broker = StubBroker()
    engine = ExecutionEngine(db_session, broker)
    asset = _add_asset(db_session, "AAPL")
    bot = _make_bot(db_session)

    outcome = engine.enter(
        bot,
        asset_id=asset.id,
        ticker="AAPL",
        symbol="AAPL",
        shares=0,
        price=100.0,
        now=_NOW,
        reason="x",
    )

    assert outcome.action == "noop"
    assert bot.is_flat
    assert bot.cash == 100_000.0


def test_exit_sells_fully_credits_cash_and_realises_pnl(
    db_session: Session,
) -> None:
    broker = StubBroker()
    engine = ExecutionEngine(db_session, broker)
    asset = _add_asset(db_session, "AAPL")
    bot = _make_bot(db_session)
    price = broker.get_quote("AAPL").last
    assert price is not None

    engine.enter(
        bot,
        asset_id=asset.id,
        ticker="AAPL",
        symbol="AAPL",
        shares=10,
        price=price,
        now=_NOW,
        reason="up cross",
    )
    cash_after_buy = bot.cash
    pos = bot.positions[0]
    # Pretend the entry was below the current quote so the sale realises a gain.
    pos.avg_price = price - 5.0

    outcome = engine.exit(bot, pos, now=_NOW, reason="down cross")

    assert outcome.action == "exit"
    assert bot.is_flat
    assert bot.cash == cash_after_buy + 10 * price
    assert bot.realised_pnl == (price - (price - 5.0)) * 10
    assert bot.total_trades == 2
    assert bot.trades[-1].side == "sell"


# Pure value helpers ------------------------------------------------------
def test_unrealised_and_total_value_sum_across_positions(
    db_session: Session,
) -> None:
    bot = _make_bot(db_session, cash=1_000.0)
    bot.positions.append(
        BotPosition(
            asset_id=1, ticker="AAA", alpaca_symbol="AAA",
            quantity=10, avg_price=50.0, opened_at=_NOW,
        )
    )
    bot.positions.append(
        BotPosition(
            asset_id=2, ticker="BBB", alpaca_symbol="BBB",
            quantity=5, avg_price=20.0, opened_at=_NOW,
        )
    )
    marks = {"AAA": 60.0, "BBB": 15.0}

    # (60-50)*10 + (15-20)*5 = 100 - 25 = 75
    assert unrealised_pnl(bot, marks) == 75.0
    # cash 1000 + 60*10 + 15*5 = 1000 + 600 + 75 = 1675
    assert total_value(bot, marks) == 1_675.0


def test_total_value_falls_back_to_avg_price_when_unmarked(
    db_session: Session,
) -> None:
    bot = _make_bot(db_session, cash=500.0)
    bot.positions.append(
        BotPosition(
            asset_id=1, ticker="AAA", alpaca_symbol="AAA",
            quantity=10, avg_price=50.0, opened_at=_NOW,
        )
    )
    # No mark for AAA → valued at cost, zero unrealised.
    assert unrealised_pnl(bot, {}) == 0.0
    assert total_value(bot, {}) == 500.0 + 10 * 50.0


def test_take_profit_stop_loss_reason() -> None:
    assert (
        take_profit_stop_loss_reason(
            avg_price=100.0, price=110.0, take_profit_pct=0.05, stop_loss_pct=0.05
        )
        == REASON_TAKE_PROFIT
    )
    assert (
        take_profit_stop_loss_reason(
            avg_price=100.0, price=90.0, take_profit_pct=0.05, stop_loss_pct=0.05
        )
        == REASON_STOP_LOSS
    )
    assert (
        take_profit_stop_loss_reason(
            avg_price=100.0, price=102.0, take_profit_pct=0.05, stop_loss_pct=0.05
        )
        is None
    )
    # Thresholds unset never trigger.
    assert (
        take_profit_stop_loss_reason(
            avg_price=100.0, price=500.0, take_profit_pct=None, stop_loss_pct=None
        )
        is None
    )
