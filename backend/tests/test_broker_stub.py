"""Tests for the deterministic in-memory :class:`StubBroker`."""

from __future__ import annotations

import pytest

from cadence.broker import Broker, StubBroker, get_broker
from cadence.broker.base import OrderError
from cadence.broker.models import OrderStatus


def test_stub_satisfies_broker_protocol() -> None:
    assert isinstance(StubBroker(), Broker)


def test_deterministic_quotes_are_stable() -> None:
    broker = StubBroker()
    first = broker.get_quote("AAPL")
    second = broker.get_quote("AAPL")
    assert first.last == second.last
    assert first.last is not None and first.last > 0
    # Distinct symbols generally differ; the price is purely symbol-derived.
    assert broker.get_quote("AAPL").last != broker.get_quote("ZZZZ").last


def test_is_market_open_always_true() -> None:
    assert StubBroker().is_market_open() is True


def test_buy_updates_positions_and_cash_deterministically() -> None:
    broker = StubBroker(initial_cash=100_000.0)
    price = broker.get_quote("AAPL").last
    assert price is not None

    order = broker.buy("AAPL", 10)

    assert order.status == OrderStatus.FILLED
    assert order.filled_quantity == 10
    assert order.filled_price == price

    position = broker.get_position("AAPL")
    assert position is not None
    assert position.quantity == 10
    assert position.avg_cost == price

    account = broker.get_account_info()
    assert account.cash_balance == pytest.approx(100_000.0 - 10 * price)


def test_sell_reduces_position_and_returns_cash() -> None:
    broker = StubBroker(initial_cash=100_000.0)
    price = broker.get_quote("MSFT").last
    assert price is not None

    broker.buy("MSFT", 10)
    broker.sell("MSFT", 4)

    position = broker.get_position("MSFT")
    assert position is not None
    assert position.quantity == 6

    account = broker.get_account_info()
    # Bought 10, sold 4 at the same deterministic price -> net 6 held.
    assert account.cash_balance == pytest.approx(100_000.0 - 6 * price)


def test_sell_more_than_held_raises() -> None:
    broker = StubBroker()
    broker.buy("TSLA", 1)
    with pytest.raises(OrderError):
        broker.sell("TSLA", 5)


def test_buy_beyond_buying_power_raises() -> None:
    broker = StubBroker(initial_cash=100.0)
    with pytest.raises(OrderError):
        broker.buy("AAPL", 1_000)


def test_get_broker_returns_stub_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from cadence import config

    monkeypatch.setattr(config.settings, "ALPACA_STUB", True)
    assert isinstance(get_broker(), StubBroker)
