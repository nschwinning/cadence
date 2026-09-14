"""Tests for :class:`AlpacaBroker` using a fake ``requests`` session.

No real network calls are made: a fake session records requests and returns
canned JSON, letting us assert URL/auth selection and response parsing.
"""

from __future__ import annotations

from typing import Any

import pytest

from cadence.broker import AlpacaBroker
from cadence.broker.base import ConnectionError
from cadence.broker.models import OrderSide, OrderStatus, OrderType


class FakeResponse:
    """Minimal stand-in for a ``requests.Response``."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.text = "{}" if payload is not None else ""

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class FakeSession:
    """Records calls and returns queued/mapped canned responses."""

    def __init__(self, routes: dict[tuple[str, str], Any]) -> None:
        # Keyed by (method, endpoint-suffix) -> payload.
        self._routes = routes
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        for (route_method, suffix), payload in self._routes.items():
            if route_method == method and url.endswith(suffix):
                return FakeResponse(payload)
        raise AssertionError(f"Unexpected request: {method} {url}")


def _make_broker(routes: dict[tuple[str, str], Any]) -> tuple[AlpacaBroker, FakeSession]:
    session = FakeSession(routes)
    broker = AlpacaBroker(
        api_key="test-key",
        secret_key="test-secret",
        paper=True,
        session=session,
    )
    return broker, session


def test_missing_api_key_raises() -> None:
    with pytest.raises(ConnectionError):
        AlpacaBroker(api_key="", secret_key="secret", session=object())


def test_blank_secret_key_raises() -> None:
    with pytest.raises(ConnectionError):
        AlpacaBroker(api_key="key", secret_key="   ", session=object())


def test_paper_selects_paper_base_url() -> None:
    broker, session = _make_broker({("GET", "/v2/clock"): {"is_open": True}})
    broker.is_market_open()
    assert session.calls[0]["url"].startswith("https://paper-api.alpaca.markets")


def test_live_selects_live_base_url() -> None:
    session = FakeSession({("GET", "/v2/clock"): {"is_open": False}})
    broker = AlpacaBroker(
        api_key="k", secret_key="s", paper=False, session=session
    )
    broker.is_market_open()
    assert session.calls[0]["url"].startswith("https://api.alpaca.markets")


def test_auth_headers_are_sent() -> None:
    broker, session = _make_broker({("GET", "/v2/clock"): {"is_open": True}})
    broker.is_market_open()
    headers = session.calls[0]["headers"]
    assert headers["APCA-API-KEY-ID"] == "test-key"
    assert headers["APCA-API-SECRET-KEY"] == "test-secret"


def test_is_market_open_reads_clock() -> None:
    broker, _ = _make_broker({("GET", "/v2/clock"): {"is_open": True}})
    assert broker.is_market_open() is True

    broker2, _ = _make_broker({("GET", "/v2/clock"): {"is_open": False}})
    assert broker2.is_market_open() is False


def test_submit_order_maps_response_to_order() -> None:
    order_response = {
        "id": "abc-123",
        "symbol": "AAPL",
        "side": "buy",
        "qty": "10",
        "type": "market",
        "time_in_force": "day",
        "status": "filled",
        "submitted_at": "2026-09-14T10:00:00Z",
        "filled_qty": "10",
        "filled_avg_price": "150.25",
    }
    broker, session = _make_broker({("POST", "/v2/orders"): order_response})

    order = broker.buy("AAPL", 10)

    assert order.order_id == "abc-123"
    assert order.broker_order_id == "abc-123"
    assert order.status == OrderStatus.FILLED
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.MARKET
    assert order.filled_quantity == 10
    assert order.filled_price == 150.25
    assert order.submitted_at is not None

    # The submitted payload carried the expected order fields.
    payload = session.calls[0]["json"]
    assert payload["symbol"] == "AAPL"
    assert payload["qty"] == "10"
    assert payload["side"] == "buy"
    assert payload["type"] == "market"
    assert payload["time_in_force"] == "day"


def test_get_account_info_parses_fields() -> None:
    account_response = {
        "id": "acct-9",
        "cash": "5000.50",
        "buying_power": "10000.00",
        "portfolio_value": "15000.00",
        "unrealized_pl": "250.00",
        "realized_pl": "100.00",
        "currency": "USD",
    }
    broker, _ = _make_broker({("GET", "/v2/account"): account_response})

    info = broker.get_account_info()
    assert info.account_id == "acct-9"
    assert info.cash_balance == 5000.50
    assert info.buying_power == 10000.00
    assert info.portfolio_value == 15000.00
    assert info.is_paper is True


def test_get_quote_uses_data_host_and_parses_bid_ask() -> None:
    quote_response = {"quote": {"bp": 149.9, "ap": 150.1, "t": "2026-09-14T10:00:00Z"}}
    broker, session = _make_broker(
        {("GET", "/v2/stocks/AAPL/quotes/latest"): quote_response}
    )

    quote = broker.get_quote("AAPL")
    assert quote.symbol == "AAPL"
    assert quote.bid == 149.9
    assert quote.ask == 150.1
    assert session.calls[0]["url"].startswith("https://data.alpaca.markets")
